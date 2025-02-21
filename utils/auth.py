import os
import requests
import streamlit as st
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class INaturalistAuth:
    BASE_URL = "https://www.inaturalist.org"

    def __init__(self):
        """Initialize auth with optional API token."""
        self.client_id = os.environ.get("INATURALIST_APP_ID")
        self.client_secret = os.environ.get("INATURALIST_APP_SECRET")
        self.redirect_uri = "https://inat-taxa-trees.replit.app/callback"

    @staticmethod
    def init_auth_state():
        """Initialize authentication state in session."""
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if "access_token" not in st.session_state:
            st.session_state.access_token = None
        if "api_token" not in st.session_state:
            st.session_state.api_token = None
        if "target_username" not in st.session_state:
            st.session_state.target_username = None
        if "username" not in st.session_state:
            st.session_state.username = None

    @staticmethod
    def authenticate_with_token(api_token: str) -> bool:
        """Authenticate using an API token."""
        try:
            # Test the token by making a request to the /users/me endpoint
            response = requests.get(
                "https://api.inaturalist.org/v1/users/me",
                headers={"Authorization": f"Bearer {api_token}"}
            )
            
            if response.status_code == 200:
                st.session_state.api_token = api_token
                st.session_state.authenticated = True
                st.session_state.access_token = api_token
                username = response.json()['results'][0]['login']
                st.session_state.username = username
                logger.info(f"Successfully authenticated with API token for user {username}")
                return True
            else:
                logger.error(f"Token authentication failed with status {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Error authenticating with token: {str(e)}")
            return False

    @staticmethod
    def is_authenticated() -> bool:
        """Check if the user is authenticated."""
        return st.session_state.get("authenticated", False)

    @staticmethod
    def get_access_token() -> str:
        """Get the stored access token or API token."""
        return st.session_state.get("access_token") or st.session_state.get("api_token")

    @staticmethod
    def logout() -> None:
        """Clear the stored authentication data."""
        st.session_state.authenticated = False
        st.session_state.access_token = None
        st.session_state.api_token = None
        st.session_state.username = None
        st.session_state.target_username = None

def get_auth_headers():
    """Get authentication headers if token is available."""
    token = st.session_state.get('access_token') or st.session_state.get('api_token')
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}