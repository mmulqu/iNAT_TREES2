from typing import Dict, List, Optional, Set
import json
from datetime import datetime, timezone
import psycopg2
from psycopg2.extras import Json
import os

class TaxonomyCache:
    def __init__(self):
        self.conn = psycopg2.connect(os.environ["DATABASE_URL"])

    def get_cached_tree(self, root_id: int) -> Optional[Dict]:
        """Retrieve a cached taxonomy tree for a given root ID."""
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT complete_subtree, last_updated
                FROM taxonomy_structure
                WHERE root_id = %s
            """, (root_id,))
            result = cur.fetchone()
            
            if result:
                return result[0]  # Return the complete_subtree JSONB
        return None

    def save_tree(self, root_id: int, tree: Dict, species_count: int):
        """Save a complete taxonomy tree to the cache."""
        with self.conn as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO taxonomy_structure 
                    (root_id, complete_subtree, species_count, last_updated, confidence_complete)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (root_id) DO UPDATE
                    SET complete_subtree = EXCLUDED.complete_subtree,
                        species_count = EXCLUDED.species_count,
                        last_updated = EXCLUDED.last_updated,
                        confidence_complete = EXCLUDED.confidence_complete
                """, (
                    root_id,
                    Json(tree),
                    species_count,
                    datetime.now(timezone.utc),
                    True
                ))

    @staticmethod
    def filter_tree(complete_tree: Dict, user_species_ids: List[int]) -> Optional[Dict]:
        """Filter a complete taxonomic tree to only show branches leading to user's species."""
        def prune_tree(node: Dict, keep_species: Set[int]) -> Optional[Dict]:
            if node.get('rank') == 'species':
                return node if node.get('id') in keep_species else None
                
            pruned_children = {}
            for child_id, child in node.get('children', {}).items():
                pruned_child = prune_tree(child, keep_species)
                if pruned_child:
                    pruned_children[child_id] = pruned_child
                    
            if pruned_children:
                filtered_node = node.copy()
                filtered_node['children'] = pruned_children
                return filtered_node
            return None

        return prune_tree(complete_tree, set(user_species_ids))

    def get_filtered_user_tree(self, root_id: int, user_species_ids: List[int]) -> Optional[Dict]:
        """Get a filtered tree showing only the user's observations."""
        complete_tree = self.get_cached_tree(root_id)
        if complete_tree:
            return self.filter_tree(complete_tree, user_species_ids)
        return None
