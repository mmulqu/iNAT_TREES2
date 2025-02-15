import requests
from typing import Dict, List, Optional
import time

class INaturalistAPI:
    BASE_URL = "https://api.inaturalist.org/v1"

    @staticmethod
    def get_user_observations(username: str, taxonomic_group: str = None, per_page: int = 200) -> List[Dict]:
        """Fetch observations for a given iNaturalist username with optional taxonomic filtering."""
        # Using taxon_ids for more precise filtering
        taxon_params = {
            "Insects": 47158,     # Class Insecta
            "Fungi": 47170,       # Kingdom Fungi
            "Plants": 47126,      # Kingdom Plantae
            "Mammals": 40151,     # Class Mammalia
            "Reptiles": 26036,    # Class Reptilia
            "Amphibians": 20978   # Class Amphibia
        }

        observations = []
        page = 1

        while True:
            try:
                params = {
                    "user_login": username,
                    "per_page": per_page,
                    "page": page,
                    "order": "desc",
                    "order_by": "created_at",
                    "includes": "taxon,ancestors"  # Request full ancestor data
                }

                if taxonomic_group in taxon_params:
                    params["taxon_id"] = taxon_params[taxonomic_group]

                response = requests.get(
                    f"{INaturalistAPI.BASE_URL}/observations",
                    params=params
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