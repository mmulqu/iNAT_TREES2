import json
from typing import Dict, List, Optional, Set
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json
import os

class TaxonomyCache:
    def __init__(self):
        self.conn = None
        self.connect()

    def connect(self) -> bool:
        """Establish database connection with proper error handling."""
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
                self._ensure_tables()
                return True
        except Exception as e:
            print(f"TaxonomyCache database connection error: {e}")
            self.conn = None
        return False

    def _ensure_tables(self):
        """Ensure all required tables and indices exist."""
        try:
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
            if self.conn:
                self.conn.rollback()

    def get_cached_tree(self, root_id: int, max_age_days: int = 30) -> Optional[Dict]:
        """Retrieve a cached taxonomy tree with age validation."""
        if not self.connect():
            return None

        try:
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
                if result and result[2]:  # Check confidence_complete flag
                    return {
                        'tree': result[0],
                        'ancestor_chain': result[4] or []
                    }
        except Exception as e:
            print(f"Error retrieving cached tree: {e}")
        return None

    def build_tree_from_taxa(self, root_id: int, species_ids: List[int]) -> Optional[Dict]:
        """Build complete taxonomy tree from taxa table."""
        if not self.connect():
            return None

        try:
            print(f"Building tree for root {root_id} with {len(species_ids)} species")

            # Initialize tree with root node
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT name, rank, common_name
                    FROM taxa
                    WHERE taxon_id = %s
                """, (root_id,))
                root_data = cur.fetchone()
                if not root_data:
                    print(f"Root taxon {root_id} not found")
                    return None

                tree = {
                    'id': root_id,
                    'name': root_data[0],
                    'rank': root_data[1],
                    'common_name': root_data[2],
                    'children': {}
                }

            # Get all species and their ancestors
            species_nodes = {}
            for species_id in species_ids:
                with self.conn.cursor() as cur:
                    cur.execute("""
                        SELECT taxon_id, name, rank, common_name, ancestor_ids
                        FROM taxa
                        WHERE taxon_id = %s
                    """, (species_id,))
                    species_data = cur.fetchone()

                    if species_data:
                        species_nodes[species_id] = {
                            'id': species_id,
                            'name': species_data[1],
                            'rank': 'species',
                            'common_name': species_data[3],
                            'ancestor_ids': species_data[4] or []
                        }

            # Build tree structure
            for species_id, species_node in species_nodes.items():
                current_level = tree['children']
                ancestor_ids = species_node['ancestor_ids']

                for ancestor_id in ancestor_ids:
                    if ancestor_id == root_id:
                        continue

                    if ancestor_id not in current_level:
                        # Get ancestor data
                        with self.conn.cursor() as cur:
                            cur.execute("""
                                SELECT name, rank, common_name
                                FROM taxa
                                WHERE taxon_id = %s
                            """, (ancestor_id,))
                            ancestor_data = cur.fetchone()
                            if ancestor_data:
                                current_level[ancestor_id] = {
                                    'id': ancestor_id,
                                    'name': ancestor_data[0],
                                    'rank': ancestor_data[1],
                                    'common_name': ancestor_data[2],
                                    'children': {}
                                }
                    if ancestor_id in current_level:
                        current_level = current_level[ancestor_id]['children']

                # Add species node
                if species_id not in current_level:
                    current_level[species_id] = {
                        'id': species_id,
                        'name': species_node['name'],
                        'rank': 'species',
                        'common_name': species_node['common_name'],
                        'children': {}
                    }

            return tree
        except Exception as e:
            print(f"Error building tree: {e}")
            return None

    def save_tree(self, root_id: int, tree: Dict, species_ids: List[int]):
        """Save complete taxonomy tree."""
        if not self.connect():
            return

        try:
            # Get ancestor chain from the first species (they should share common ancestors)
            ancestor_chain = set()
            if species_ids:
                with self.conn.cursor() as cur:
                    cur.execute("""
                        SELECT ancestor_ids
                        FROM taxa
                        WHERE taxon_id = %s
                    """, (species_ids[0],))
                    result = cur.fetchone()
                    if result and result[0]:
                        ancestor_chain.update(result[0])

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
                        sorted(list(ancestor_chain))
                    ))
        except Exception as e:
            print(f"Error saving tree: {e}")
            if self.conn:
                self.conn.rollback()

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """Get a filtered tree for user species."""
        if not self.connect():
            return None

        try:
            cache_key = f"{root_id}_{sorted(user_species_ids)}"

            # Check filtered trees cache
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

            # Build tree if not cached
            tree = self.build_tree_from_taxa(root_id, user_species_ids)
            if not tree:
                return None

            # Save complete tree
            self.save_tree(root_id, tree, user_species_ids)

            # Filter tree
            filtered_tree = self._filter_tree(tree, set(user_species_ids))
            if filtered_tree:
                try:
                    with self.conn as conn:
                        with conn.cursor() as cur:
                            cur.execute("""
                                INSERT INTO filtered_trees (cache_key, filtered_tree)
                                VALUES (%s, %s)
                                ON CONFLICT (cache_key) 
                                DO UPDATE SET 
                                    filtered_tree = EXCLUDED.filtered_tree,
                                    created_at = CURRENT_TIMESTAMP
                            """, (cache_key, Json(filtered_tree)))
                except Exception as e:
                    print(f"Error caching filtered tree: {e}")

            return filtered_tree
        except Exception as e:
            print(f"Error getting filtered tree: {e}")
            return None

    def _filter_tree(self, tree: Dict, species_ids: Set[int]) -> Optional[Dict]:
        """Filter tree to only include paths to specified species."""
        def prune_tree(node: Dict) -> Optional[Dict]:
            if node.get('rank') == 'species':
                return node if node.get('id') in species_ids else None

            pruned_children = {}
            for child_id, child in node.get('children', {}).items():
                pruned_child = prune_tree(child)
                if pruned_child:
                    pruned_children[child_id] = pruned_child

            if pruned_children:
                filtered_node = node.copy()
                filtered_node['children'] = pruned_children
                return filtered_node
            return None

        return prune_tree(tree)