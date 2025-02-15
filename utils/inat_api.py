import requests
from typing import Dict, List, Optional
import time

class INaturalistAPI:
    BASE_URL = "https://api.inaturalist.org/v1"
    
    @staticmethod
    def get_user_observations(username: str, per_page: int = 200) -> List[Dict]:
        """Fetch observations for a given iNaturalist username."""
        observations = []
        page = 1
        
        while True:
            try:
                response = requests.get(
                    f"{INaturalistAPI.BASE_URL}/observations",
                    params={
                        "user_login": username,
                        "per_page": per_page,
                        "page": page,
                        "order": "desc",
                        "order_by": "created_at"
                    }
                )
                response.raise_for_status()
                data = response.json()
                
                if not data["results"]:
                    break
                    
                observations.extend(data["results"])
                
                if len(data["results"]) < per_page:
                    break
                    
                page += 1
                time.sleep(1)  # Rate limiting
                
            except requests.RequestException as e:
                raise Exception(f"Error fetching observations: {str(e)}")
                
        return observations

    @staticmethod
    def get_taxon_details(taxon_id: int) -> Optional[Dict]:
        """Fetch detailed information about a specific taxon."""
        try:
            response = requests.get(f"{INaturalistAPI.BASE_URL}/taxa/{taxon_id}")
            response.raise_for_status()
            return response.json()["results"][0]
        except requests.RequestException:
            return None
