
import os
import psycopg2
from psycopg2.extras import DictCursor, Json
from typing import Optional, Dict, List
import json
from datetime import datetime, timezone

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
                parent_id INTEGER REFERENCES taxa(id),
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cached_branches (
                species_id INTEGER PRIMARY KEY,
                branch_data JSONB NOT NULL,
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            )
            """)
            self.conn.commit()

    def get_cached_branch(self, species_id: int) -> Optional[Dict]:
        """Retrieve cached branch information for a species."""
        self.connect()
        if not self.conn:
            return None
        
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
            SELECT branch_data
            FROM cached_branches
            WHERE species_id = %s
            """, (species_id,))
            result = cur.fetchone()
            if result:
                return result[0]
        return None

    def save_branch(self, species_id: int, branch_data: Dict):
        """Save branch information to the database."""
        self.connect()
        if not self.conn:
            return
        
        with self.conn.cursor() as cur:
            cur.execute("""
            INSERT INTO cached_branches (species_id, branch_data, last_updated)
            VALUES (%s, %s, %s)
            ON CONFLICT (species_id) DO UPDATE
            SET branch_data = EXCLUDED.branch_data,
                last_updated = EXCLUDED.last_updated
            """, (species_id, Json(branch_data), datetime.now(timezone.utc)))
            self.conn.commit()

    def get_taxon(self, taxon_id: int) -> Optional[Dict]:
        """Retrieve taxon information from the database."""
        self.connect()
        if not self.conn:
            return None
        
        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
            SELECT id, name, rank, common_name, parent_id
            FROM taxa
            WHERE id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            if result:
                return dict(result)
        return None

    def save_taxon(self, taxon_id: int, name: str, rank: str, common_name: Optional[str] = None, parent_id: Optional[int] = None):
        """Save taxon information to the database."""
        self.connect()
        if not self.conn:
            return
        
        with self.conn.cursor() as cur:
            cur.execute("""
            INSERT INTO taxa (id, name, rank, common_name, parent_id)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE
            SET name = EXCLUDED.name,
                rank = EXCLUDED.rank,
                common_name = EXCLUDED.common_name,
                parent_id = EXCLUDED.parent_id
            """, (taxon_id, name, rank, common_name, parent_id))
            self.conn.commit()
