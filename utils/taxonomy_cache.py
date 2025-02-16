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
                DO $$ 
                BEGIN
                    CREATE TABLE IF NOT EXISTS taxonomy_structure (
                        root_id INTEGER PRIMARY KEY,
                        complete_subtree JSONB NOT NULL,
                        species_count INTEGER NOT NULL,
                        last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                        confidence_complete BOOLEAN DEFAULT FALSE,
                        CONSTRAINT valid_species_count CHECK (species_count >= 0)
                    );

                    -- Add ancestor_chain column if it doesn't exist
                    IF NOT EXISTS (
                        SELECT 1 
                        FROM information_schema.columns 
                        WHERE table_name='taxonomy_structure' 
                        AND column_name='ancestor_chain'
                    ) THEN
                        ALTER TABLE taxonomy_structure 
                        ADD COLUMN ancestor_chain INTEGER[] NOT NULL DEFAULT '{}';
                    END IF;

                    -- Create filtered_trees table if it doesn't exist
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

                CREATE INDEX IF NOT EXISTS filtered_trees_created_idx 
                ON filtered_trees(created_at);
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
            """, (root_id, max_age_days))

            result = cur.fetchone()
            if result and result[2]:  # Check confidence_complete flag
                return {
                    'tree': result[0],
                    'ancestor_chain': result[4] or []
                }
        return None

    def get_ancestors(self, taxon_id: int) -> List[int]:
        """Get ancestor IDs for a given taxon from the taxa table."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ancestor_ids
                FROM taxa
                WHERE taxon_id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            return result[0] if result else []

    def build_ancestor_chain(self, species_id: int) -> List[int]:
        """Build complete ancestor chain for a species."""
        ancestors = self.get_ancestors(species_id)
        if not ancestors:
            return []

        # Add the species itself to the chain
        chain = [species_id]

        # Process each ancestor
        for ancestor_id in ancestors:
            chain.append(ancestor_id)
            parent_ancestors = self.get_ancestors(ancestor_id)
            chain.extend(parent_ancestors)

        # Remove duplicates while preserving order
        return list(dict.fromkeys(chain))

    def save_tree(self, root_id: int, tree: Dict, species_ids: List[int]):
        """Save a complete taxonomy tree with ancestor chains."""
        # Build unique ancestor chains for all species
        all_chains = set()
        for species_id in species_ids:
            chain = self.build_ancestor_chain(species_id)
            all_chains.update(chain)

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
                    list(all_chains)
                ))

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """Get a filtered tree for user species with ancestor chain validation."""
        cache_key = f"{root_id}_{sorted(user_species_ids)}"

        # Check cached filtered tree
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

        # Get complete tree and validate against ancestor chains
        cached_data = self.get_cached_tree(root_id)
        if not cached_data:
            return None

        complete_tree = cached_data['tree']
        ancestor_chain = set(cached_data['ancestor_chain'])

        # Validate species are in the ancestor chain
        valid_species = [
            species_id for species_id in user_species_ids 
            if species_id in ancestor_chain
        ]

        if not valid_species:
            return None

        filtered_tree = self._filter_tree_efficient(complete_tree, set(valid_species))

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
        """Optimized tree filtering with ancestor chain validation."""
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

        return prune_tree(complete_tree)