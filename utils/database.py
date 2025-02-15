import os
import psycopg2
from psycopg2.extras import DictCursor
from typing import Optional, Dict

class Database:
    _instance = None
    
    def __init__(self):
        self.conn = psycopg2.connect(os.environ["DATABASE_URL"])
        self.create_tables()
    
    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    def create_tables(self):
        """Create the necessary tables if they don't exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS taxa (
                id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                rank VARCHAR(50) NOT NULL,
                common_name VARCHAR(255),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """)
            self.conn.commit()
    
    def get_taxon(self, taxon_id: int) -> Optional[Dict]:
        """Retrieve taxon information from the database."""
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
            SELECT id, name, rank, common_name
            FROM taxa
            WHERE id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            if result:
                return dict(result)
            return None
    
    def save_taxon(self, taxon_id: int, name: str, rank: str, common_name: Optional[str] = None):
        """Save taxon information to the database."""
        with self.conn.cursor() as cur:
            cur.execute("""
            INSERT INTO taxa (id, name, rank, common_name)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                rank = EXCLUDED.rank,
                common_name = EXCLUDED.common_name
            """, (taxon_id, name, rank, common_name))
            self.conn.commit()
