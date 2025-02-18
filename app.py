import sys
import logging
import os
import random
import threading
import time

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

try:
    logger.info("Importing required packages...")
    import streamlit as st
    import plotly.graph_objects as go
    from utils.inat_api import INaturalistAPI
    from utils.data_processor import DataProcessor
    from utils.tree_builder import TreeBuilder
    logger.info("All imports successful")
except Exception as e:
    logger.error(f"Failed to import required packages: {str(e)}")
    sys.exit(1)

# Helper: Rotating spinner messages
FETCH_MESSAGES = [
    "Fetching observations... At this rate, entire new species might evolve before we finish.",
    "Still loading... Darwin would've published another book in this time.",
    "Connecting to iNaturalist... The sloth is our spirit animal right now.",
    "Retrieving your data... This is taking longer than continental drift.",
    "Loading observations... If only data traveled as fast as invasive species.",
    "Fetching... Remember when naturalists had to do this with pencil and paper?",
    "Still working... Even lichens grow faster than this API response.",
    "Gathering data... Approximately 42 species have gone extinct during this wait.",
    "Retrieving observations... We're moving at a geological pace here.",
    "Loading... Stare long enough and you might witness screen evolution."
]

PROCESS_MESSAGES = [
    "Processing data... Taxonomists from the 1800s would've finished faster with a quill pen.",
    "Crunching numbers... This tree is more stubborn than convergent evolution.",
    "Processing... We're experiencing Lamarckian levels of adaptation here.",
    "Building your tree... Less 'survival of the fittest' and more 'survival of the patient'.",
    "Sorting species... Moving slower than a three-toed sloth after Thanksgiving dinner.",
    "Processing... Charles Darwin waited 20 years to publish, so this isn't so bad, right?",
    "Analyzing data... If phylogeny is the tree of life, we're still watering the seed.",
    "Still working... Feeling like we're stuck in the Precambrian era of loading screens.",
    "Processing... This is taking longer than speciation in Darwin's finches.",
    "Calculating relationships... Moving at the pace of punctuated equilibrium."
]

def get_random_message(message_list):
    return random.choice(message_list)

# Page configuration
try:
    logger.info("Starting Streamlit application...")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Current working directory: {os.getcwd()}")

    st.set_page_config(
        page_title="iNaturalist Phylogenetic Tree Viewer",
        page_icon="🌳",
        layout="wide"
    )

    # Load custom CSS
    try:
        logger.info("Loading custom CSS...")
        with open("assets/style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception as e:
        logger.error(f"Error loading CSS: {e}")
        st.warning("Custom styling could not be loaded, but the app will continue to function.")

    # Initialize session state
    if 'observations' not in st.session_state:
        st.session_state.observations = None
        logger.info("Initialized session state")

    # Header
    st.markdown('<h1 class="main-header">iNaturalist Phylogenetic Tree Viewer 🌳</h1>', unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown('<h2 class="subheader">Settings</h2>', unsafe_allow_html=True)
        username = st.text_input("iNaturalist Username")
        taxonomic_group = st.selectbox(
            "Select Taxonomic Group",
            ["All Groups", "Insects", "Fungi", "Plants", "Mammals", "Reptiles", "Amphibians", "Mollusks"]
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
            logger.info(f"Processing request for username: {username}, group: {taxonomic_group}")

            # Fetch observations if not already in session state
            if not st.session_state.observations:
                spinner_message = get_random_message(FETCH_MESSAGES)
                with st.spinner(spinner_message):
                    filter_group = None if taxonomic_group == "All Groups" else taxonomic_group
                    api = INaturalistAPI()  # Create instance first
                    st.session_state.observations = api.get_user_observations(username, filter_group)
            observations = st.session_state.observations
            logger.info(f"Retrieved {len(observations) if observations else 0} observations")

            if not observations:
                st.markdown("""
                <div class="error-box">
                    No observations found for this username. Please check the username and try again.
                </div>
                """, unsafe_allow_html=True)
            else:
                # Process data with taxonomic filter
                spinner_message = get_random_message(PROCESS_MESSAGES)
                with st.spinner(spinner_message):
                    filter_group = None if taxonomic_group == "All Groups" else taxonomic_group
                    df = DataProcessor.process_observations(observations, filter_group)
                    logger.info(f"Processed data into DataFrame with {len(df)} rows")

                    if df.empty:
                        st.warning(f"No observations found for {taxonomic_group}. Try selecting a different group.")
                    else:
                        hierarchy = DataProcessor.build_taxonomy_hierarchy(df)
                        logger.info("Built taxonomy hierarchy")

                        # Create and display tree
                        fig = TreeBuilder.create_plotly_tree(hierarchy)
                        st.plotly_chart(fig, use_container_width=True)

                        # Display statistics
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Total Species", len(df))
                        with col2:
                            st.metric("Unique Families", df["family"].nunique() if "family" in df.columns else 0)
                        with col3:
                            st.metric("Unique Orders", df["order"].nunique() if "order" in df.columns else 0)

            # Optional: if you use threads, ensure you join them only if started.
            if "process_thread" in st.session_state:
                process_thread = st.session_state.process_thread
                if process_thread.is_alive():
                    process_thread.join()

        except Exception as e:
            logger.error(f"Error in main app flow: {str(e)}", exc_info=True)
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

except Exception as e:
    logger.error(f"Critical error in app startup: {str(e)}", exc_info=True)
    st.error(f"Critical error: {str(e)}")
