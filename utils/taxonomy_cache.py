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
            # Create taxonomy_structure table with improved schema
            cur.execute("""
                CREATE TABLE IF NOT EXISTS taxonomy_structure (
                    root_id INTEGER PRIMARY KEY,
                    complete_subtree JSONB NOT NULL,
                    species_count INTEGER NOT NULL,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    confidence_complete BOOLEAN DEFAULT FALSE,
                    ancestor_chain INTEGER[] NOT NULL DEFAULT '{}',
                    CONSTRAINT valid_species_count CHECK (species_count >= 0)
                );

                CREATE INDEX IF NOT EXISTS taxonomy_ancestor_chain_idx 
                ON taxonomy_structure USING GIN(ancestor_chain);

                CREATE INDEX IF NOT EXISTS taxonomy_subtree_idx 
                ON taxonomy_structure USING GIN(complete_subtree jsonb_path_ops);
            """)
            self.conn.commit()

    def get_cached_tree(self, root_id: int, max_age_days: int = 30) -> Optional[Dict]:
        """
        Retrieve a cached taxonomy tree with age validation.

        Args:
            root_id: The root taxon ID to retrieve
            max_age_days: Maximum age of cached data in days
        """
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT 
                    complete_subtree,
                    last_updated,
                    confidence_complete,
                    species_count
                FROM taxonomy_structure
                WHERE root_id = %s
                AND last_updated > NOW() - INTERVAL '%s days'
            """, (root_id, max_age_days))

            result = cur.fetchone()
            if result and result[2]:  # Check confidence_complete flag
                return result[0]
        return None

    def build_ancestor_chain(self, species_id: int) -> List[int]:
        """Build complete ancestor chain for a species using cached data."""
        with self.conn.cursor() as cur:
            cur.execute("""
                WITH RECURSIVE ancestry AS (
                    SELECT 
                        taxon_id,
                        ancestor_ids,
                        1 as level
                    FROM taxa
                    WHERE taxon_id = %s

                    UNION

                    SELECT 
                        t.taxon_id,
                        t.ancestor_ids,
                        a.level + 1
                    FROM taxa t
                    INNER JOIN ancestry a ON t.taxon_id = ANY(a.ancestor_ids)
                    WHERE t.rank != 'species'
                )
                SELECT DISTINCT taxon_id
                FROM ancestry
                ORDER BY level DESC;
            """, (species_id,))

            return [row[0] for row in cur.fetchall()]

    def save_tree(self, root_id: int, tree: Dict, species_ids: List[int]):
        """
        Save a complete taxonomy tree with improved metadata.

        Args:
            root_id: The root taxon ID
            tree: The complete taxonomy tree
            species_ids: List of species IDs in the tree
        """
        # Build ancestor chains for all species
        ancestor_chains = set()
        for species_id in species_ids:
            chain = self.build_ancestor_chain(species_id)
            ancestor_chains.update(chain)

        with self.conn as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO taxonomy_structure 
                    (root_id, complete_subtree, species_count, last_updated, 
                     confidence_complete, ancestor_chain)
                    VALUES (%s, %s, %s, %s, %s, %s)
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
                    True,
                    list(ancestor_chains)
                ))

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """
        Get an efficiently filtered tree for user species with caching.

        Args:
            root_id: The root taxon ID
            user_species_ids: List of species IDs to include
        """
        # First check if we have a cached filtered tree for this exact combination
        cache_key = f"{root_id}_{sorted(user_species_ids)}"

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT filtered_tree
                FROM filtered_trees
                WHERE cache_key = %s
                AND created_at > NOW() - INTERVAL '1 day'
            """, (cache_key,))

            cached = cur.fetchone()
            if cached:
                return cached[0]

        # If no cached filtered tree, get the complete tree and filter it
        complete_tree = self.get_cached_tree(root_id)
        if not complete_tree:
            return None

        filtered_tree = self._filter_tree_efficient(complete_tree, set(user_species_ids))

        # Cache the filtered tree
        if filtered_tree:
            with self.conn as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO filtered_trees (cache_key, filtered_tree)
                        VALUES (%s, %s)
                        ON CONFLICT (cache_key) 
                        DO UPDATE SET filtered_tree = EXCLUDED.filtered_tree,
                                    created_at = CURRENT_TIMESTAMP
                    """, (cache_key, Json(filtered_tree)))

        return filtered_tree

    def _filter_tree_efficient(self, complete_tree: Dict, keep_species: Set[int]) -> Optional[Dict]:
        """Optimized tree filtering with path caching."""
        valid_paths = set()

        def find_valid_paths(node: Dict, current_path: List[int]):
            node_id = node.get('id')
            if not node_id:
                return

            current_path.append(node_id)

            if node.get('rank') == 'species' and node_id in keep_species:
                valid_paths.update(current_path)

            for child in node.get('children', {}).values():
                find_valid_paths(child, current_path.copy())

        # First pass: identify all valid paths
        find_valid_paths(complete_tree, [])

        def prune_tree(node: Dict) -> Optional[Dict]:
            node_id = node.get('id')
            if not node_id or node_id not in valid_paths:
                return None

            pruned_children = {}
            for child_id, child in node.get('children', {}).items():
                pruned_child = prune_tree(child)
                if pruned_child:
                    pruned_children[child_id] = pruned_child

            if pruned_children or node.get('rank') == 'species':
                filtered_node = node.copy()
                filtered_node['children'] = pruned_children
                return filtered_node

            return None

        # Second pass: create filtered tree
        return prune_tree(complete_tree)