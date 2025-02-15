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
                st.session_state.observations = INaturalistAPI.get_user_observations(username)

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
""", unsafe_allow_html=True)