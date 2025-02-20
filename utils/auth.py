import os
import requests
from typing import Optional, Dict, Any
import streamlit as st

class INaturalistAuth:
    INATURALIST_BASE_URL = "https://www.inaturalist.org"

    @staticmethod
    def get_authorization_url() -> str:
        """Generate the authorization URL for iNaturalist OAuth2."""
        client_id = os.environ["INATURALIST_APP_ID"]
        # Use the full URL including protocol and hostname
        base_url = st.get_option('server.baseUrlPath')
        # Remove any trailing slash
        base_url = base_url.rstrip('/')
        redirect_uri = f"{base_url}/callback"

        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code"
        }

        # Construct query string
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{INaturalistAuth.INATURALIST_BASE_URL}/oauth/authorize?{query_string}"

    @staticmethod
    def exchange_code_for_token(code: str) -> Optional[Dict[str, Any]]:
        """Exchange the authorization code for an access token."""
        try:
            base_url = st.get_option('server.baseUrlPath')
            base_url = base_url.rstrip('/')
            redirect_uri = f"{base_url}/callback"

            payload = {
                "client_id": os.environ["INATURALIST_APP_ID"],
                "client_secret": os.environ["INATURALIST_APP_SECRET"],
                "code": code,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }

            response = requests.post(
                f"{INaturalistAuth.INATURALIST_BASE_URL}/oauth/token",
                data=payload
            )

            if response.status_code == 200:
                return response.json()
            return None

        except Exception as e:
            st.error(f"Error exchanging code for token: {str(e)}")
            return None

    @staticmethod
    def is_authenticated() -> bool:
        """Check if the user is authenticated."""
        return "access_token" in st.session_state

    @staticmethod
    def get_access_token() -> Optional[str]:
        """Get the stored access token."""
        return st.session_state.get("access_token")

    @staticmethod
    def store_token(token_data: Dict[str, Any]) -> None:
        """Store the token data in session state."""
        st.session_state["access_token"] = token_data.get("access_token")

    @staticmethod
    def logout() -> None:
        """Clear the stored authentication data."""
        if "access_token" in st.session_state:
            del st.session_state["access_token"]