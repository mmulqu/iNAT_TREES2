
import os
import requests
import streamlit as st
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class INaturalistAuth:
    BASE_URL = "https://www.inaturalist.org"

    def __init__(self):
        self.client_id = os.environ["INATURALIST_APP_ID"]
        self.client_secret = os.environ["INATURALIST_APP_SECRET"]
        self.redirect_uri = "https://inat-taxa-trees.replit.app/callback"

    @staticmethod
    def get_authorization_url() -> str:
        """Generate the authorization URL for iNaturalist OAuth."""
        auth = INaturalistAuth()
        params = {
            "client_id": auth.client_id,
            "redirect_uri": auth.redirect_uri,
            "response_type": "code"
        }
        auth_url = f"{INaturalistAuth.BASE_URL}/oauth/authorize?{urlencode(params)}"
        logger.info(f"Generated authorization URL: {auth_url}")
        return auth_url

    def exchange_code_for_token(self, code: str) -> dict:
        """Exchange the authorization code for an access token."""
        try:
            payload = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": self.redirect_uri,
                "grant_type": "authorization_code"
            }

            response = requests.post(
                f"{self.BASE_URL}/oauth/token",
                data=payload
            )

            if response.status_code == 200:
                return response.json()
            logger.error(f"Token exchange failed with status {response.status_code}: {response.text}")
            return None

        except Exception as e:
            logger.error(f"Error exchanging code for token: {str(e)}")
            st.error(f"Error exchanging code for token: {str(e)}")
            return None

    @staticmethod
    def init_auth_state():
        """Initialize authentication state in session."""
        if "authenticated" not in st.session_state:
            st.session_state.authenticated = False
        if "access_token" not in st.session_state:
            st.session_state.access_token = None

    @staticmethod
    def is_authenticated() -> bool:
        """Check if the user is authenticated."""
        return st.session_state.get("authenticated", False)

    @staticmethod
    def get_access_token() -> str:
        """Get the stored access token."""
        return st.session_state.get("access_token")

    @staticmethod
    def store_token(token_data: dict) -> None:
        """Store the token data and user info in session state."""
        st.session_state.access_token = token_data.get("access_token")
        st.session_state.authenticated = True
        
        # Fetch and store user info
        try:
            me_response = requests.get(
                "https://api.inaturalist.org/v1/users/me",
                headers={"Authorization": f"Bearer {token_data['access_token']}"}
            )
            if me_response.status_code == 200:
                username = me_response.json()['results'][0]['login']
                st.session_state.username = username
                logger.info(f"Stored username in session state: {username}")
            else:
                logger.error(f"Failed to fetch user info: {me_response.status_code}")
        except Exception as e:
            logger.error(f"Error fetching user info: {str(e)}")

    @staticmethod
    def logout() -> None:
        """Clear the stored authentication data."""
        st.session_state.authenticated = False
        if "access_token" in st.session_state:
            del st.session_state.access_token

def get_auth_headers():
    """Get authentication headers if token is available."""
    if st.session_state.get('access_token'):
        return {"Authorization": f"Bearer {st.session_state.access_token}"}
    return {}
