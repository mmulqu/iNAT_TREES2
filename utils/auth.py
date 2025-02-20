
import os
import requests
import streamlit as st
import logging
from urllib.parse import urlencode

logger = logging.getLogger(__name__)

class INaturalistAuth:
    BASE_URL = "https://www.inaturalist.org"

    @staticmethod
    def get_authorization_url() -> str:
        """Generate the authorization URL for iNaturalist OAuth2."""
        client_id = os.environ["INATURALIST_APP_ID"]
        
        # Get the full deployment URL from Streamlit
        base_url = st.get_option("server.baseUrlPath")
        if base_url.startswith('/'):
            # We're in a deployment environment
            base_url = f"https://{os.environ.get('REPL_SLUG')}-00-{os.environ.get('REPL_ID')}.picard.repl.dev"
        
        redirect_uri = f"{base_url}/callback"
        logger.info(f"Generated redirect URI: {redirect_uri}")

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code"
        }

        auth_url = f"{INaturalistAuth.BASE_URL}/oauth/authorize?{urlencode(params)}"
        logger.info(f"Generated authorization URL: {auth_url}")
        return auth_url

    @staticmethod
    def exchange_code_for_token(code: str) -> dict:
        """Exchange the authorization code for an access token."""
        try:
            base_url = st.get_option('server.baseUrlPath')
            base_url = base_url.rstrip('/')
            redirect_uri = f"{base_url}/callback"

            logger.info(f"Exchange token redirect URI: {redirect_uri}")

            payload = {
                "client_id": os.environ["INATURALIST_APP_ID"],
                "client_secret": os.environ["INATURALIST_APP_SECRET"],
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }

            response = requests.post(
                f"{INaturalistAuth.BASE_URL}/oauth/token",
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
    def is_authenticated() -> bool:
        """Check if the user is authenticated."""
        return "access_token" in st.session_state

    @staticmethod
    def get_access_token() -> str:
        """Get the stored access token."""
        return st.session_state.get("access_token")

    @staticmethod
    def store_token(token_data: dict) -> None:
        """Store the token data in session state."""
        st.session_state["access_token"] = token_data.get("access_token")

    @staticmethod
    def logout() -> None:
        """Clear the stored authentication data."""
        if "access_token" in st.session_state:
            del st.session_state["access_token"]
