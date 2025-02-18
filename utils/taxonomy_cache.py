from typing import Dict, List, Optional
import json
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json
import os

class TaxonomyCache:
    def __init__(self):
        """Initialize database connection and ensure tables exist."""
        self.conn = None
        self.connect()
        self._ensure_tables()

    def connect(self):
        """Establish database connection."""
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
        except Exception as e:
            print(f"Database connection error: {e}")
            self.conn = None

    def _ensure_tables(self):
        """Create necessary tables if they don't exist."""
        try:
            with self.conn.cursor() as cur:
                # Table for caching complete trees.
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS filtered_trees (
                        cache_key TEXT PRIMARY KEY,
                        filtered_tree JSONB NOT NULL,
                        created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE INDEX IF NOT EXISTS filtered_trees_created_idx 
                        ON filtered_trees(created_at);
                """)
                self.conn.commit()
        except Exception as e:
            print(f"Error creating tables: {e}")

    def get_cached_tree(self, root_id: int, max_age_days: int = 30) -> Optional[Dict]:
        """Retrieve a cached complete tree using the root_id as key."""
        try:
            with self.conn.cursor() as cur:
                query = """
                    SELECT filtered_tree, created_at
                    FROM filtered_trees
                    WHERE cache_key = %s
                """
                cur.execute(query, (str(root_id),))
                result = cur.fetchone()
                if result:
                    tree_data, created_at = result
                    print(f"Found cached tree for root_id {root_id} from {created_at}")
                    return tree_data
                print(f"No cached tree found for root_id {root_id}")
                return None
        except Exception as e:
            print(f"Error retrieving cached tree: {e}")
            return None

    def save_tree(self, root_id: int, tree: Dict) -> None:
        """Save a complete tree to the 'filtered_trees' table using the root_id as key."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO filtered_trees (cache_key, filtered_tree)
                    VALUES (%s, %s)
                    ON CONFLICT (cache_key) 
                    DO UPDATE SET 
                        filtered_tree = EXCLUDED.filtered_tree,
                        created_at = NOW()
                """, (
                    str(root_id),
                    Json(tree)
                ))
                self.conn.commit()
                print(f"Saved complete tree to cache with root {root_id}")
        except Exception as e:
            print(f"Error saving tree to cache: {e}")

    def get_ancestors(self, species_id: int) -> Optional[List[Dict]]:
        """
        Retrieve the cached ancestor information for a species.
        Instead of using a full 'ancestor_data' structure,
        we now only use the ancestor_ids stored in the taxa table.
        """
        from utils.database import Database  # Avoid circular dependency
        db = Database.get_instance()
        cached_data = db.get_cached_branch(species_id)
        if cached_data and cached_data.get("ancestor_ids"):
            print(f"Found cached ancestor_ids for species {species_id}")
            ancestors = []
            for aid in cached_data.get("ancestor_ids"):
                ancestor = db.get_cached_branch(aid)
                if ancestor:
                    ancestors.append({
                        "id": ancestor["id"],
                        "name": ancestor["name"],
                        "rank": ancestor["rank"],
                        "preferred_common_name": ancestor.get("common_name", "")
                    })
            return ancestors
        print(f"No cached ancestor data found for species {species_id}")
        return None

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """Get a filtered tree for specific species, using cached data when possible."""
        if not user_species_ids:
            print("No species IDs provided for filtering")
            return None

        # Create a cache key based on root_id and sorted species_ids
        cache_key = f"{root_id}_{','.join(sorted(map(str, user_species_ids)))}"

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
                # For simplicity, return the cached tree.
                return result[0]
        return None

    def _get_ancestor_chain(self, species_id: int) -> List[Dict]:
        """
        Retrieve the full ancestor chain for a species using the stored ancestor_ids.
        Returns a list of minimal dictionaries (id, name, rank) for each ancestor.
        """
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

            ancestor_chain = []
            for ancestor_id in result[0]:
                ancestor_info = self._get_node_info(ancestor_id)
                if ancestor_info:
                    ancestor_chain.append({
                        "id": ancestor_id,
                        "name": ancestor_info["name"],
                        "rank": ancestor_info["rank"]
                    })
            # Sort by taxonomic rank using a predefined order
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
        """Retrieve node information from the taxa table."""
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
        """Retrieve the name for a taxon from the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT name 
                FROM taxa 
                WHERE taxon_id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            return result[0] if result else str(taxon_id)

    def _get_taxon_rank(self, taxon_id: int) -> str:
        """Retrieve the rank for a taxon from the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT rank 
                FROM taxa 
                WHERE taxon_id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            return result[0] if result else ""

    def _filter_tree_for_species(self, tree: Dict, keep_species: set) -> Optional[Dict]:
        """Filter a taxonomic tree to only include paths to the specified species."""
        if not isinstance(tree, dict) or not keep_species:
            return None

        print(f"Filtering tree to include only {len(keep_species)} species")

        valid_taxa = set()

        def find_valid_paths(node, current_path):
            if not isinstance(node, dict) or "id" not in node:
                return
            current_path = current_path + [node["id"]]
            if node.get("rank") == "species" and node["id"] in keep_species:
                valid_taxa.update(current_path)
            for child in node.get("children", {}).values():
                find_valid_paths(child, current_path)

        find_valid_paths(tree, [])
        print(f"Found {len(valid_taxa)} taxa in paths to target species")

        def filter_node(node):
            if not isinstance(node, dict) or "id" not in node:
                return None
            if node["id"] not in valid_taxa:
                return None
            filtered = {
                "id": node["id"],
                "name": node.get("name", ""),
                "rank": node.get("rank", ""),
                "common_name": node.get("common_name", ""),
                "children": {}
            }
            for key, child in node.get("children", {}).items():
                filtered_child = filter_node(child)
                if filtered_child:
                    filtered["children"][key] = filtered_child
            return filtered

        return filter_node(tree)
