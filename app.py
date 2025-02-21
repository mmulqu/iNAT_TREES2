import sys
import logging
import os
import time
import requests
from urllib.parse import urlparse, parse_qs

# Configure logging first
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

try:
    logger.info("Importing required packages...")
    import streamlit as st
    import plotly.graph_objects as go
    from utils.inat_api import INaturalistAPI
    from utils.data_processor import DataProcessor
    from utils.tree_builder import TreeBuilder
    from utils.auth import INaturalistAuth
    logger.info("All imports successful")
except Exception as e:
    logger.error(f"Failed to import required packages: {str(e)}")
    sys.exit(1)

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

    # Initialize session state variables
    INaturalistAuth.init_auth_state()
    if 'observations' not in st.session_state:
        st.session_state.observations = None
    if 'last_username' not in st.session_state:
        st.session_state.last_username = ""
    if 'last_taxonomic_group' not in st.session_state:
        st.session_state.last_taxonomic_group = ""

    # Header
    st.markdown('<h1 class="main-header">iNaturalist Phylogenetic Tree Viewer 🌳</h1>', unsafe_allow_html=True)

    # Authentication section
    if not INaturalistAuth.is_authenticated():
        st.warning("Please authenticate with your iNaturalist API token to continue.")
        
        with st.form("auth_form"):
            api_token = st.text_input("Enter your iNaturalist API token:", type="password",
                                    help="You can find your API token in your iNaturalist account settings")
            submit_button = st.form_submit_button("Authenticate")
            
            if submit_button and api_token:
                if INaturalistAuth.authenticate_with_token(api_token):
                    st.success(f"Successfully authenticated as {st.session_state.username}!")
                    st.rerun()
                else:
                    st.error("Invalid API token. Please check and try again.")
        
        st.markdown("""
        ### How to get your API token:
        1. Log in to your iNaturalist account
        2. Go to Account Settings
        3. Navigate to the "Developer" section
        4. Find your API token or create a new one
        """)
    else:
        # Add logout button in sidebar
        with st.sidebar:
            st.text(f"Logged in as: {st.session_state.username}")
            if st.button("Logout"):
                INaturalistAuth.logout()
                st.rerun()

        # Main interface
        with st.sidebar:
            st.markdown('<h2 class="subheader">Settings</h2>', unsafe_allow_html=True)
            
            # Username input
            target_username = st.text_input(
                "iNaturalist Username to analyze:",
                value=st.session_state.get('target_username', st.session_state.username),
                help="Enter any iNaturalist username to analyze their observations"
            )
            
            # Store the target username in session state
            if target_username != st.session_state.get('target_username'):
                st.session_state.target_username = target_username
                st.session_state.observations = None  # Clear cached observations
            
            taxonomic_group = st.selectbox(
                "Select Taxonomic Group",
                ["All Groups", "Insects", "Fungi", "Plants", "Mammals", "Reptiles", 
                 "Amphibians", "Mollusks", "Birds", "Spiders", "Fish"]
            )
            
            run_button = st.button("Generate Tree")
            
            st.markdown("""
            <div class="info-box">
                Enter any iNaturalist username and select a group of organisms to visualize their observations.
            </div>
            """, unsafe_allow_html=True)

        # Main content
        if run_button:
            try:
                if not st.session_state.get('authenticated', False):
                    st.error("Please authenticate first")
                    st.stop()
                
                if not st.session_state.target_username:
                    st.error("Please enter a username to analyze")
                    st.stop()

                logger.info(f"Processing request for target user {st.session_state.target_username}, group: {taxonomic_group}")

                # Check if parameters have changed
                if (st.session_state.last_username != st.session_state.target_username or 
                    st.session_state.last_taxonomic_group != taxonomic_group):
                    logger.info("New parameters detected. Clearing cached observations.")
                    st.session_state.observations = None
                    st.session_state.last_username = st.session_state.target_username
                    st.session_state.last_taxonomic_group = taxonomic_group

                # Fetch observations if not already in session state
                if not st.session_state.observations:
                    spinner_messages = [
                        "Fetching observations... At this rate, entire new species might evolve before we finish.",
                        "Still loading... Darwin would've published another book in this time.",
                        "Connecting to iNaturalist... The sloth is our spirit animal right now.",
                        "Retrieving your data... This is taking longer than continental drift.",
                        "Loading observations... If only data traveled as fast as invasive species."
                    ]
                    with st.spinner(spinner_messages[0]):
                        logger.info(f"Calling API for username: {st.session_state.target_username}")
                        api = INaturalistAPI()
                        st.session_state.observations = api.get_user_observations(
                            username=st.session_state.target_username,
                            taxonomic_group=None if taxonomic_group == "All Groups" else taxonomic_group
                        )

                observations = st.session_state.observations
                logger.info(f"Retrieved {len(observations) if observations else 0} observations")

                if not observations:
                    st.markdown("""
                    <div class="error-box">
                        No observations found. Please try a different taxonomic group or check the username.
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    # Process data with taxonomic filter
                    with st.spinner("Processing data... Moving at the pace of a peer-reviewed publication—circa 1850."):
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
                                st.metric("Unique Families", df["family"].nunique() if "family" in df.columns else "N/A")
                            with col3:
                                st.metric("Unique Orders", df["order"].nunique() if "order" in df.columns else "N/A")

            except Exception as e:
                logger.error(f"Error in main app flow: {str(e)}", exc_info=True)
                st.markdown(f"""
                <div class="error-box">
                    An error occurred: {str(e)}
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