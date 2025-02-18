from typing import Dict, List, Optional, Set
import json
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json
import os

class TaxonomyCache:
    def __init__(self):
        self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
        self._ensure_tables()

    def _ensure_tables(self):
        """Ensure all required tables and indices exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
                DO $$ 
                BEGIN
                    CREATE TABLE IF NOT EXISTS taxonomy_structure (
                        root_id INTEGER PRIMARY KEY,
                        complete_subtree JSONB NOT NULL,
                        species_count INTEGER NOT NULL,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        confidence_complete BOOLEAN DEFAULT FALSE,
                        ancestor_chain INTEGER[] NOT NULL DEFAULT '{}'
                    );

                    CREATE TABLE IF NOT EXISTS species_ancestors (
                        species_id INTEGER,
                        root_id INTEGER,
                        ancestor_chain INTEGER[] NOT NULL,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (species_id, root_id)
                    );

                    CREATE TABLE IF NOT EXISTS filtered_trees (
                        cache_key TEXT PRIMARY KEY,
                        filtered_tree JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                END $$;

                -- Create necessary indices
                CREATE INDEX IF NOT EXISTS taxonomy_ancestor_chain_idx 
                ON taxonomy_structure USING GIN(ancestor_chain);

                CREATE INDEX IF NOT EXISTS taxonomy_subtree_idx 
                ON taxonomy_structure USING GIN(complete_subtree jsonb_path_ops);

                CREATE INDEX IF NOT EXISTS species_ancestors_root_idx 
                ON species_ancestors(root_id);

                CREATE INDEX IF NOT EXISTS filtered_trees_created_idx 
                ON filtered_trees(created_at);
            """)
            self.conn.commit()

    def get_ancestors(self, species_id: int) -> Optional[List[Dict]]:
        """Get cached ancestor information for a species."""
        from utils.database import Database  # Import here to avoid circular dependency

        db = Database.get_instance()
        cached_data = db.get_cached_branch(species_id)

        if cached_data and cached_data.get("ancestor_data"):
            print(f"Found cached ancestor data for species {species_id}")
            return cached_data["ancestor_data"]

        # If we don't have detailed ancestor data, try to get just the ancestor chain
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ancestor_chain
                FROM species_ancestors
                WHERE species_id = %s
                ORDER BY last_updated DESC
                LIMIT 1
            """, (species_id,))

            result = cur.fetchone()
            if result and result[0]:
                print(f"Found cached ancestor chain for species {species_id}")
                # Convert ancestor IDs to basic ancestor information
                ancestors = []
                for ancestor_id in result[0]:
                    ancestor_data = db.get_cached_branch(ancestor_id)
                    if ancestor_data:
                        ancestors.append({
                            "id": ancestor_id,
                            "name": ancestor_data["name"],
                            "rank": ancestor_data["rank"],
                            "preferred_common_name": ancestor_data["common_name"]
                        })
                return ancestors

        print(f"No cached ancestor data found for species {species_id}")
        return None

    def get_cached_tree(self, root_id: int, max_age_days: int = 30) -> Optional[Dict]:
        """Retrieve a cached taxonomy tree with age validation."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    complete_subtree,
                    last_updated,
                    confidence_complete,
                    species_count,
                    ancestor_chain
                FROM taxonomy_structure
                WHERE root_id = %s
                AND last_updated > NOW() - INTERVAL '%s days'
            """, (root_id, max_age_days))

            result = cur.fetchone()
            if result:
                print(f"Found cached tree for root_id {root_id} from {result[1]}")
                return {
                    'tree': result[0],
                    'last_updated': result[1],
                    'confidence_complete': result[2],
                    'species_count': result[3],
                    'ancestor_chain': result[4] or []
                }
        print(f"No cached tree found for root_id {root_id}")
        return None

    def save_tree(self, root_id: int, tree: Dict, species_ids: List[int]):
        """Save a complete taxonomy tree with species relationships."""
        print(f"Saving tree for root_id {root_id} with {len(species_ids)} species")

        # Validate the tree has the minimum required structure
        if not isinstance(tree, dict) or "id" not in tree:
            print("Error: Invalid tree structure")
            return

        # Build ancestor chains for all species
        all_ancestor_ids = self._collect_all_ancestor_ids(tree)

        try:
            with self.conn:
                with self.conn.cursor() as cur:
                    # Save the main tree structure
                    cur.execute("""
                        INSERT INTO taxonomy_structure 
                        (root_id, complete_subtree, species_count, last_updated, 
                         confidence_complete, ancestor_chain)
                        VALUES (%s, %s, %s, %s, TRUE, %s)
                        ON CONFLICT (root_id) DO UPDATE
                        SET complete_subtree = EXCLUDED.complete_subtree,
                            species_count = EXCLUDED.species_count,
                            last_updated = EXCLUDED.last_updated,
                            confidence_complete = EXCLUDED.confidence_complete,
                            ancestor_chain = EXCLUDED.ancestor_chain
                    """, (
                        root_id,
                        Json(tree),
                        len(species_ids),
                        datetime.now(timezone.utc),
                        list(all_ancestor_ids)
                    ))
                    print(f"Saved tree structure for root_id {root_id}")

                    # Save relationships for each species
                    for species_id in species_ids:
                        # Get ancestors for this species from the tree
                        ancestors = self._find_ancestors_for_species(tree, species_id)
                        if ancestors:
                            cur.execute("""
                                INSERT INTO species_ancestors 
                                (species_id, root_id, ancestor_chain, last_updated)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT (species_id, root_id) DO UPDATE
                                SET ancestor_chain = EXCLUDED.ancestor_chain,
                                    last_updated = EXCLUDED.last_updated
                            """, (
                                species_id,
                                root_id,
                                ancestors + [species_id],  # Include the species itself
                                datetime.now(timezone.utc)
                            ))
            print(f"Successfully saved tree and species relationships")
        except Exception as e:
            print(f"Error saving tree: {e}")

    def _collect_all_ancestor_ids(self, tree: Dict) -> Set[int]:
        """Collect all taxon IDs in the tree."""
        all_ids = set()

        def traverse(node):
            if isinstance(node, dict) and "id" in node:
                all_ids.add(node["id"])
                for child in node.get("children", {}).values():
                    traverse(child)

        traverse(tree)
        return all_ids

    def _find_ancestors_for_species(self, tree: Dict, species_id: int) -> List[int]:
        """Find the ancestor chain for a specific species in the tree."""
        ancestors = []

        def traverse(node, current_path):
            if not isinstance(node, dict) or "id" not in node:
                return False

            new_path = current_path + [node["id"]]

            # Check if this is the species we're looking for
            if node["id"] == species_id and node.get("rank") == "species":
                ancestors.extend(current_path)
                return True

            # Check children
            for child in node.get("children", {}).values():
                if traverse(child, new_path):
                    return True

            return False

        traverse(tree, [])
        return ancestors

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """Get a filtered tree for specific species, using cached data when possible."""
        if not user_species_ids:
            print("No species IDs provided for filtering")
            return None

        # Create a cache key based on root_id and sorted species_ids
        cache_key = f"{root_id}_{','.join(sorted(map(str, user_species_ids)))}"

        # Check if we have a cached filtered tree
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT filtered_tree
                FROM filtered_trees
                WHERE cache_key = %s
                AND created_at > NOW() - INTERVAL '7 days'
            """, (cache_key,))

            result = cur.fetchone()
            if result:
                print(f"Found cached filtered tree for {len(user_species_ids)} species")

                # Start with Life as the root
                root_tree = {
                    "id": 48460,
                    "name": "Life",
                    "rank": "stateofmatter",
                    "children": {}
                }

                # Add the standard taxonomic levels
                animals_node = {
                    "id": 1,
                    "name": "Animalia",
                    "rank": "kingdom",
                    "children": {}
                }
                root_tree["children"]["1"] = animals_node

                mollusks_node = {
                    "id": 47115,
                    "name": "Mollusks",
                    "rank": "phylum",
                    "children": {}
                }
                animals_node["children"]["47115"] = mollusks_node

                # Process each species and build its full taxonomic path
                for species_id in user_species_ids:
                    # Get the species info and its ancestors
                    species_info = self._get_node_info(species_id)
                    if not species_info:
                        continue

                    # Get ancestor chain for this species
                    ancestor_chain = self._get_ancestor_chain(species_id)
                    if not ancestor_chain:
                        continue

                    # Build the path from mollusks down to species
                    current_node = mollusks_node
                    for ancestor in ancestor_chain:
                        # Skip Life, Animals, and Mollusks as they're already in the tree
                        if ancestor["id"] in {48460, 1, 47115}:
                            continue

                        ancestor_id = str(ancestor["id"])
                        if ancestor_id not in current_node["children"]:
                            current_node["children"][ancestor_id] = {
                                "id": ancestor["id"],
                                "name": ancestor["name"],
                                "rank": ancestor["rank"],
                                "children": {}
                            }
                        current_node = current_node["children"][ancestor_id]

                    # Add the species as a leaf node
                    species_node = {
                        "id": species_id,
                        "name": species_info["name"],
                        "rank": "species",
                        "children": {}
                    }
                    current_node["children"][str(species_id)] = species_node

                return root_tree

            return None

    def _get_ancestor_chain(self, species_id: int) -> List[Dict]:
        """Get the full ancestor chain for a species in taxonomic order."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ancestor_chain
                FROM species_ancestors
                WHERE species_id = %s
                ORDER BY last_updated DESC
                LIMIT 1
            """, (species_id,))
            result = cur.fetchone()
            if not result or not result[0]:
                return []

            # Get info for each ancestor
            ancestor_chain = []
            for ancestor_id in result[0]:
                ancestor_info = self._get_node_info(ancestor_id)
                if ancestor_info:
                    ancestor_chain.append({
                        "id": ancestor_id,
                        "name": ancestor_info["name"],
                        "rank": ancestor_info["rank"]
                    })

            # Sort by taxonomic rank
            rank_order = {
                "stateofmatter": 0,
                "kingdom": 1,
                "phylum": 2,
                "class": 3,
                "order": 4,
                "family": 5,
                "genus": 6,
                "species": 7
            }
            ancestor_chain.sort(key=lambda x: rank_order.get(x["rank"], 999))
            return ancestor_chain

    def _get_node_info(self, node_id: int) -> Optional[Dict]:
        """Get node information from the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT name, rank, common_name
                FROM taxa
                WHERE taxon_id = %s
            """, (node_id,))
            result = cur.fetchone()
            if result:
                return {
                    "name": result[0],
                    "rank": result[1],
                    "common_name": result[2] if len(result) > 2 else ""
                }
            return None

    def _get_taxon_name(self, taxon_id: int) -> str:
        """Get the name for a taxon ID from the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT name 
                FROM taxa 
                WHERE taxon_id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            return result[0] if result else str(taxon_id)

    def _get_taxon_rank(self, taxon_id: int) -> str:
        """Get the rank for a taxon ID from the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT rank 
                FROM taxa 
                WHERE taxon_id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            return result[0] if result else ""

    def _filter_tree_for_species(self, tree: Dict, keep_species: Set[int]) -> Optional[Dict]:
        """Filter tree to only include paths to specified species."""
        if not isinstance(tree, dict) or not keep_species:
            return None

        print(f"Filtering tree to include only {len(keep_species)} species")

        # First, find all paths to the target species
        valid_taxa = set()

        def find_valid_paths(node, current_path):
            if not isinstance(node, dict) or "id" not in node:
                return

            current_path = current_path + [node["id"]]

            # If this is a target species, mark its entire path as valid
            if node.get("rank") == "species" and node["id"] in keep_species:
                valid_taxa.update(current_path)

            # Process children
            for child in node.get("children", {}).values():
                find_valid_paths(child, current_path)

        find_valid_paths(tree, [])
        print(f"Found {len(valid_taxa)} taxa in paths to target species")

        # Then create a filtered tree with only the valid paths
        def filter_node(node):
            if not isinstance(node, dict) or "id" not in node:
                return None

            if node["id"] not in valid_taxa:
                return None

            # Create a copy of this node
            filtered = {
                "id": node["id"],
                "name": node.get("name", ""),
                "rank": node.get("rank", ""),
                "common_name": node.get("common_name", ""),
                "children": {}
            }

            # Filter children
            for key, child in node.get("children", {}).items():
                filtered_child = filter_node(child)
                if filtered_child:
                    filtered["children"][key] = filtered_child

            return filtered

        return filter_node(tree)