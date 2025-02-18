import os
import psycopg2
from psycopg2.extras import DictCursor, Json
from typing import Optional, Dict
from datetime import datetime, timezone
from utils.data_utils import normalize_ancestors  # Import from data_utils instead

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

    def get_cached_branch(self, taxon_id: int) -> Optional[Dict]:
        """Get a cached taxon branch from the database."""
        try:
            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT name, rank, common_name, ancestor_ids, ancestor_data
                    FROM taxa
                    WHERE taxon_id = %s
                """, (taxon_id,))

                result = cur.fetchone()
                if result:
                    name, rank, common_name, ancestor_ids, ancestor_data = result

                    # Ensure ancestor_data is properly structured
                    normalized_ancestors = []
                    if ancestor_data and 'ancestor_data' in ancestor_data:
                        normalized_ancestors = ancestor_data['ancestor_data']

                    # Return consistent structure
                    return {
                        'id': taxon_id,
                        'name': name,
                        'rank': rank,
                        'common_name': common_name,
                        'ancestor_ids': ancestor_ids or [],
                        'ancestors': normalized_ancestors
                    }

        except Exception as e:
            print(f"Error getting cached branch for {taxon_id}: {e}")
        return None

    def save_branch(self, taxon_id: int, taxon_data: Dict) -> None:
        """Save a taxon branch to the database only if it doesn't already exist."""
        try:
            with self.conn.cursor() as cur:
                # Check if this taxon already exists
                cur.execute("""
                    SELECT taxon_id FROM taxa WHERE taxon_id = %s
                """, (taxon_id,))
                existing = cur.fetchone()

                if existing:
                    print(f"Taxon {taxon_id} already exists in cache")
                    return

                # Normalize ancestor data before saving.
                # Assume your normalize_ancestors returns a list of dicts.
                normalized_ancestors = normalize_ancestors(taxon_data.get('ancestors', []))

                cur.execute("""
                    INSERT INTO taxa 
                    (taxon_id, name, rank, common_name, ancestor_ids, ancestor_data, last_updated)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (taxon_id) DO NOTHING
                """, (
                    taxon_id,
                    taxon_data.get('name', ''),
                    taxon_data.get('rank', ''),
                    taxon_data.get('preferred_common_name', ''),
                    taxon_data.get('ancestor_ids', []),
                    Json({'ancestor_data': normalized_ancestors})
                ))

                if cur.rowcount > 0:
                    print(f"Saved new taxon {taxon_id} to database")
                else:
                    print(f"Taxon {taxon_id} already exists in cache")
        except Exception as e:
            print(f"Error saving taxon {taxon_id}: {e}")