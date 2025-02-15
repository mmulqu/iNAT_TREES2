import os
import psycopg2
from psycopg2.extras import DictCursor
from typing import Optional, Dict

class Database:
    _instance = None
    
    def __init__(self):
        self.conn = None
        self.connect()
        self.create_tables()
    
    def connect(self):
        """Establish database connection."""
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
        self.connect()  # Ensure connection is active
        if not self.conn:
            return None
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
        self.connect()  # Ensure connection is active
        if not self.conn:
            return
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
