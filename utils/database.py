import streamlit as st
import plotly.graph_objects as go
from utils.inat_api import INaturalistAPI
from utils.data_processor import DataProcessor
from utils.tree_builder import TreeBuilder
import time

# Page configuration
st.set_page_config(
    page_title="iNaturalist Phylogenetic Tree Viewer",
    page_icon="🌳",
    layout="wide"
)

# Load custom CSS
with open("assets/style.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Header
st.markdown('<h1 class="main-header">iNaturalist Phylogenetic Tree Viewer 🌳</h1>', unsafe_allow_html=True)

# Initialize session state
if 'observations' not in st.session_state:
    st.session_state.observations = None

# Sidebar
with st.sidebar:
    st.markdown('<h2 class="subheader">Settings</h2>', unsafe_allow_html=True)
    username = st.text_input("iNaturalist Username")

    taxonomic_group = st.selectbox(
        "Select Taxonomic Group",
        ["All Groups", "Insects", "Fungi", "Plants", "Mammals", "Reptiles", "Amphibians"]
    )

    run_button = st.button("Generate Tree")

    st.markdown("""
    <div class="info-box">
        Enter your iNaturalist username to visualize your observations as a phylogenetic tree.
        Select a specific group of organisms or view all your observations.
    </div>
    """, unsafe_allow_html=True)

# Main content
if username and run_button:
    try:
        # Fetch observations if not already in session state
        if not st.session_state.observations:
            with st.spinner("Fetching observations..."):
                filter_group = None if taxonomic_group == "All Groups" else taxonomic_group
                st.session_state.observations = INaturalistAPI.get_user_observations(username, filter_group)

        observations = st.session_state.observations

        if not observations:
            st.markdown("""
            <div class="error-box">
                No observations found for this username. Please check the username and try again.
            </div>
            """, unsafe_allow_html=True)
        else:
            # Process data with taxonomic filter
            with st.spinner("Processing data..."):
                filter_group = None if taxonomic_group == "All Groups" else taxonomic_group
                df = DataProcessor.process_observations(observations, filter_group)

                if df.empty:
                    st.warning(f"No observations found for {taxonomic_group}. Try selecting a different group.")
                else:
                    hierarchy = DataProcessor.build_taxonomy_hierarchy(df)

                    # Create and display tree
                    fig = TreeBuilder.create_plotly_tree(hierarchy)
                    st.plotly_chart(fig, use_container_width=True)

                    # Display statistics
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Total Species", len(df))
                    with col2:
                        st.metric("Unique Families", df["family"].nunique())
                    with col3:
                        st.metric("Unique Orders", df["order"].nunique())

    except Exception as e:
        st.markdown(f"""
        <div class="error-box">
            An error occurred: {str(e)}
        </div>
        """, unsafe_allow_html=True)
else:
    st.markdown("""
    <div class="info-box">
        👋 Welcome! This tool visualizes your iNaturalist observations as a beautiful phylogenetic tree.
        Enter your username in the sidebar and select a taxonomic group to get started.
    </div>
    """, unsafe_allow_html=True)

# Footer
st.markdown("""
<div style="text-align: center; margin-top: 2rem; padding: 1rem; background-color: #F0F4F1; border-radius: 0.5rem;">
    Made with ❤️ for nature enthusiasts
</div>
""", unsafe_allow_html=True) os
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
        """Create tables if they don't exist."""
        with self.conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS taxa (
                taxon_id INTEGER PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                rank VARCHAR(50) NOT NULL,
                common_name VARCHAR(255),
                ancestor_ids INTEGER[],
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cached_branches (
                species_id INTEGER PRIMARY KEY,
                branch_data JSONB NOT NULL,
                last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS taxa_rank_idx ON taxa(rank);
            CREATE INDEX IF NOT EXISTS taxa_ancestor_ids_idx ON taxa USING gin(ancestor_ids)
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

        try:
            with self.conn:  # This creates a transaction
                with self.conn.cursor() as cur:
                    cur.execute("""
                    INSERT INTO cached_branches (species_id, branch_data, last_updated)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (species_id) DO UPDATE
                    SET branch_data = EXCLUDED.branch_data,
                        last_updated = EXCLUDED.last_updated
                    """, (species_id, Json(branch_data), datetime.now(timezone.utc)))
        except Exception as e:
            print(f"Error saving branch: {e}")
            if self.conn:
                self.conn.rollback()

    def get_taxon(self, taxon_id: int) -> Optional[Dict]:
        """Retrieve taxon information from the database."""
        self.connect()
        if not self.conn:
            return None

        with self.conn.cursor(cursor_factory=DictCursor) as cur:
            cur.execute("""
            SELECT taxon_id, name, rank, common_name, ancestor_ids
            FROM taxa
            WHERE taxon_id = %s
            """, (taxon_id,))
            result = cur.fetchone()
            if result:
                return dict(result)
        return None

    def save_taxon(self, taxon_id: int, name: str, rank: str, common_name: Optional[str] = None, ancestor_ids: Optional[List[int]] = None):
        """Save taxon information to the database."""
        self.connect()
        if not self.conn:
            return

        with self.conn.cursor() as cur:
            cur.execute("""
            INSERT INTO taxa (taxon_id, name, rank, common_name, ancestor_ids)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (taxon_id) DO UPDATE
            SET name = EXCLUDED.name,
                rank = EXCLUDED.rank,
                common_name = EXCLUDED.common_name,
                ancestor_ids = EXCLUDED.ancestor_ids
            """, (taxon_id, name, rank, common_name, ancestor_ids))
            self.conn.commit()