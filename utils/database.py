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
        """Establish database connection with proper error handling."""
        try:
            if self.conn is None or self.conn.closed:
                self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
                return True
        except Exception as e:
            print(f"Database connection error: {e}")
            self.conn = None
        return False

    @classmethod
    def get_instance(cls):
        """Get singleton instance with connection check."""
        if cls._instance is None:
            cls._instance = cls()
        elif cls._instance.conn is None or cls._instance.conn.closed:
            cls._instance.connect()
        return cls._instance

    def create_tables(self):
        """Create necessary tables with proper connection handling."""
        if not self.connect():
            print("Failed to create tables: no database connection")
            return

        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                CREATE TABLE IF NOT EXISTS taxa (
                    taxon_id INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    rank VARCHAR(50) NOT NULL,
                    common_name VARCHAR(255),
                    ancestor_ids INTEGER[],
                    ancestor_data JSONB,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS taxa_rank_idx ON taxa(rank);
                CREATE INDEX IF NOT EXISTS taxa_ancestor_ids_idx ON taxa USING gin(ancestor_ids);
                CREATE INDEX IF NOT EXISTS taxa_ancestor_data_idx ON taxa USING gin(ancestor_data);

                CREATE TABLE IF NOT EXISTS filtered_trees (
                    cache_key TEXT PRIMARY KEY,
                    filtered_tree JSONB NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS filtered_trees_created_idx ON filtered_trees(created_at);
                """)
                self.conn.commit()
        except Exception as e:
            print(f"Error creating tables: {e}")
            if self.conn:
                self.conn.rollback()

    def get_cached_branch(self, taxon_id: int) -> Optional[Dict]:
        """Fetch cached branch data with proper error handling."""
        if not self.connect():
            return None

        try:
            with self.conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                SELECT ancestor_data, name, rank, common_name, ancestor_ids
                FROM taxa
                WHERE taxon_id = %s
                """, (taxon_id,))
                result = cur.fetchone()
                if result:
                    return {
                        "ancestor_data": result["ancestor_data"],
                        "name": result["name"],
                        "rank": result["rank"],
                        "common_name": result["common_name"],
                        "ancestor_ids": result["ancestor_ids"]
                    }
        except Exception as e:
            print(f"Error fetching cached branch: {e}")
        return None

    def save_branch(self, taxon_id: int, taxon_data: Dict):
        """Save branch data with proper error handling."""
        if not self.connect():
            return

        try:
            with self.conn:
                with self.conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO taxa 
                    (taxon_id, name, rank, common_name, ancestor_ids, ancestor_data, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (taxon_id) DO UPDATE
                    SET name = EXCLUDED.name,
                        rank = EXCLUDED.rank,
                        common_name = EXCLUDED.common_name,
                        ancestor_ids = EXCLUDED.ancestor_ids,
                        ancestor_data = EXCLUDED.ancestor_data,
                        last_updated = EXCLUDED.last_updated
                    """, (
                        taxon_id,
                        taxon_data.get('name', ''),
                        taxon_data.get('rank', ''),
                        taxon_data.get('preferred_common_name', ''),
                        taxon_data.get('ancestor_ids', []),
                        Json(taxon_data),
                        datetime.now(timezone.utc)
                    ))
        except Exception as e:
            print(f"Error saving branch: {e}")
            if self.conn:
                self.conn.rollback()