
import requests
from typing import Dict, List, Optional
import time

class INaturalistAPI:
    BASE_URL = "https://api.inaturalist.org/v1"
    taxon_cache = {}  # Class-level cache for taxon details

    @staticmethod
    def get_taxon_details(taxon_id: int) -> Optional[Dict]:
        """Fetch detailed information about a specific taxon."""
        # Check cache first
        if taxon_id in INaturalistAPI.taxon_cache:
            return INaturalistAPI.taxon_cache[taxon_id]

        try:
            response = requests.get(f"{INaturalistAPI.BASE_URL}/taxa/{taxon_id}")
            response.raise_for_status()
            result = response.json()["results"][0]
            INaturalistAPI.taxon_cache[taxon_id] = result
            return result
        except requests.RequestException:
            return None

    @staticmethod
    def get_user_observations(username: str, taxonomic_group: str = None, per_page: int = 200) -> List[Dict]:
        """Fetch observations for a given iNaturalist username with optional taxonomic filtering."""
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
                    "include": ["taxon", "ancestors"]
                }

                if taxonomic_group in taxon_params:
                    params["taxon_id"] = taxon_params[taxonomic_group]

                print(f"Making API request with params: {params}")

                response = requests.get(
                    f"{INaturalistAPI.BASE_URL}/observations",
                    params=params
                )
                response.raise_for_status()
                data = response.json()

                if not data["results"]:
                    break

                # Process observations and fetch ancestor details
                for obs in data["results"]:
                    if "taxon" in obs and "ancestor_ids" in obs["taxon"]:
                        ancestor_ids = obs["taxon"]["ancestor_ids"]
                        
                        # Fetch details for uncached taxa
                        for taxon_id in ancestor_ids:
                            if taxon_id not in INaturalistAPI.taxon_cache:
                                print(f"Fetching details for taxon {taxon_id}")
                                INaturalistAPI.get_taxon_details(taxon_id)
                                time.sleep(0.5)  # Rate limiting
                        
                        # Add ancestor details to the observation
                        obs["taxon"]["ancestors"] = [
                            INaturalistAPI.taxon_cache.get(aid, {}) 
                            for aid in ancestor_ids
                        ]
                
                observations.extend(data["results"])

                # Debug print for first observation's ancestors (only on first page)
                if page == 1 and data["results"]:
                    first_obs = data["results"][0]
                    print("\nFirst observation ancestry:")
                    print(f"Taxon: {first_obs['taxon']['name']}")
                    print("Ancestors:")
                    for ancestor in first_obs['taxon'].get('ancestors', []):
                        print(f"  {ancestor.get('rank')}: {ancestor.get('name')}")

                if len(data["results"]) < per_page:
                    break

                page += 1
                time.sleep(1)  # Rate limiting

            except requests.RequestException as e:
                raise Exception(f"Error fetching observations: {str(e)}")

        return observations
