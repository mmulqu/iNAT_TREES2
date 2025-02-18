import os
import psycopg2
from psycopg2.extras import DictCursor, Json
from typing import Optional, Dict
from datetime import datetime, timezone

class Database:
    _instance = None

    def __init__(self):
        self.conn = None
        self.connect()
        self.create_tables()

    def connect(self):
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
                # Set autocommit to True so that every transaction is immediately committed.
                self.conn.autocommit = True
        except Exception as e:
            print(f"Database connection error: {e}")
            self.conn = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        elif cls._instance.conn is None or cls._instance.conn.closed:
            cls._instance.connect()
        return cls._instance

    def create_tables(self):
        with self.conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS taxa (
                taxon_id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                rank VARCHAR(50) NOT NULL,
                common_name VARCHAR(255),
                parent_id INTEGER,
                ancestor_ids INTEGER[],
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS taxa_rank_idx ON taxa(rank);
            CREATE INDEX IF NOT EXISTS taxa_ancestor_ids_idx ON taxa USING gin(ancestor_ids);

            CREATE TABLE IF NOT EXISTS filtered_trees (
                cache_key TEXT PRIMARY KEY,
                filtered_tree JSONB NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS filtered_trees_created_idx ON filtered_trees(created_at);
            """)
            # Note: With autocommit enabled, an explicit commit is not necessary.
            # However, if you wish to be extra sure, you can leave this line.
            self.conn.commit()

    def get_cached_branch(self, taxon_id: int) -> Optional[Dict]:
        try:
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT taxon_id, name, rank, common_name, parent_id, ancestor_ids
                    FROM taxa
                    WHERE taxon_id = %s
                """, (taxon_id,))
                result = cur.fetchone()
                if result:
                    return {
                        "id": result["taxon_id"],
                        "name": result["name"],
                        "rank": result["rank"],
                        "common_name": result["common_name"],
                        "parent_id": result["parent_id"],
                        "ancestor_ids": result["ancestor_ids"] or []
                    }
        except Exception as e:
            print(f"Error getting cached branch for {taxon_id}: {e}")
        return None

    def save_branch(self, taxon_id: int, taxon_data: Dict) -> None:
        """Save a taxon record only if it doesn't already exist."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT taxon_id FROM taxa WHERE taxon_id = %s
                """, (taxon_id,))
                existing = cur.fetchone()
                if existing:
                    print(f"Taxon {taxon_id} already exists in cache")
                    return

                cur.execute("""
                    INSERT INTO taxa 
                    (taxon_id, name, rank, common_name, parent_id, ancestor_ids, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (taxon_id) DO NOTHING
                """, (
                    taxon_id,
                    taxon_data.get("name", ""),
                    taxon_data.get("rank", ""),
                    taxon_data.get("preferred_common_name", ""),
                    taxon_data.get("parent_id"),  # Provide a parent_id if available from the API
                    taxon_data.get("ancestor_ids", [])
                ))
                if cur.rowcount > 0:
                    print(f"Saved new taxon {taxon_id} to database")
                else:
                    print(f"Taxon {taxon_id} already exists in cache")
                # With autocommit enabled, the transaction is already committed.
                self.conn.commit()
        except Exception as e:
            print(f"Error saving taxon {taxon_id}: {e}")

    def get_cached_tree(self, root_id: int, max_age_days: int = 30) -> Optional[Dict]:
        """Retrieve a cached complete tree (if previously saved) using the root_id as key."""
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
        """Save a complete tree to the filtered_trees table using the root_id as key."""
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
