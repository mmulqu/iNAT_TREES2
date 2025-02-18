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
                CREATE TABLE IF NOT EXISTS taxonomy_structure (
                    root_id INTEGER PRIMARY KEY,
                    complete_subtree JSONB NOT NULL,
                    species_count INTEGER NOT NULL,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    confidence_complete BOOLEAN DEFAULT FALSE,
                    ancestor_chain INTEGER[] NOT NULL DEFAULT '{}'
                );

                CREATE INDEX IF NOT EXISTS taxonomy_ancestor_chain_idx 
                ON taxonomy_structure USING GIN(ancestor_chain);

                CREATE INDEX IF NOT EXISTS taxonomy_subtree_idx 
                ON taxonomy_structure USING GIN(complete_subtree jsonb_path_ops);

                -- Add a new table for species-specific caching
                CREATE TABLE IF NOT EXISTS species_ancestors (
                    species_id INTEGER,
                    root_id INTEGER,
                    ancestor_chain INTEGER[] NOT NULL,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (species_id, root_id)
                );

                CREATE INDEX IF NOT EXISTS species_ancestors_root_idx 
                ON species_ancestors(root_id);
            """)
            self.conn.commit()

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
                AND confidence_complete = TRUE
            """, (root_id, max_age_days))

            result = cur.fetchone()
            if result:
                return {
                    'tree': result[0],
                    'last_updated': result[1],
                    'species_count': result[3],
                    'ancestor_chain': result[4]
                }
        return None

    def save_tree(self, root_id: int, tree: Dict, species_ids: List[int]):
        """Save a complete taxonomy tree with species relationships."""
        # First, validate the tree structure
        if not self._validate_tree_structure(tree):
            raise ValueError("Invalid tree structure")

        # Build ancestor chains for each species
        species_ancestors = self._build_species_ancestors(tree)

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
                    list(set().union(*species_ancestors.values()))
                ))

                # Save individual species ancestor relationships
                for species_id, ancestors in species_ancestors.items():
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
                        list(ancestors),
                        datetime.now(timezone.utc)
                    ))

    def _validate_tree_structure(self, tree: Dict) -> bool:
        """Validate the tree structure has required fields."""
        required_fields = {'id', 'name', 'rank', 'children'}

        def validate_node(node: Dict) -> bool:
            if not all(field in node for field in required_fields):
                return False
            return all(validate_node(child) for child in node['children'].values())

        return validate_node(tree)

    def _build_species_ancestors(self, tree: Dict) -> Dict[int, Set[int]]:
        """Build a mapping of species IDs to their ancestor sets."""
        species_ancestors = {}

        def traverse(node: Dict, current_ancestors: Set[int]):
            node_id = node['id']
            new_ancestors = current_ancestors | {node_id}

            if node['rank'] == 'species':
                species_ancestors[node_id] = new_ancestors

            for child in node['children'].values():
                traverse(child, new_ancestors)

        traverse(tree, set())
        return species_ancestors

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """Get a filtered tree for specific species, using cached data when possible."""
        # First check if we have the complete tree
        cached_tree = self.get_cached_tree(root_id)
        if not cached_tree:
            return None

        # Verify species are valid for this root
        with self.conn.cursor() as cur:
            placeholders = ','.join(['%s'] * len(user_species_ids))
            cur.execute(f"""
                SELECT DISTINCT species_id
                FROM species_ancestors
                WHERE root_id = %s
                AND species_id IN ({placeholders})
            """, [root_id] + user_species_ids)

            valid_species = [row[0] for row in cur.fetchall()]

        if not valid_species:
            return None

        return self._filter_tree_for_species(cached_tree['tree'], set(valid_species))

    def _filter_tree_for_species(self, complete_tree: Dict, keep_species: Set[int]) -> Optional[Dict]:
        """Filter tree to only include paths to specified species."""
        def prune_tree(node: Dict) -> Optional[Dict]:
            if node['rank'] == 'species':
                if node['id'] in keep_species:
                    return node
                return None

            pruned_children = {}
            for child_id, child in node['children'].items():
                pruned_child = prune_tree(child)
                if pruned_child:
                    pruned_children[child_id] = pruned_child

            if pruned_children:
                filtered_node = node.copy()
                filtered_node['children'] = pruned_children
                return filtered_node

            return None

        return prune_tree(complete_tree)