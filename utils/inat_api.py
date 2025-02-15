import requests
from typing import Dict, List, Optional
import time
from utils.database import Database

class INaturalistAPI:
    BASE_URL = "https://api.inaturalist.org/v1"

    @staticmethod
    def get_taxon_details(taxon_id: int) -> Optional[Dict]:
        """Fetch detailed information about a specific taxon."""
        # Check database first
        db = Database.get_instance()
        cached_taxon = db.get_taxon(taxon_id)
        if cached_taxon:
            print(f"Found taxon {taxon_id} in database cache")
            return cached_taxon

        try:
            print(f"Fetching taxon {taxon_id} from API")
            response = requests.get(f"{INaturalistAPI.BASE_URL}/taxa/{taxon_id}")
            response.raise_for_status()
            result = response.json()["results"][0]

            # Save to database
            db.save_taxon(
                taxon_id=result["id"],
                name=result["name"],
                rank=result["rank"],
                common_name=result.get("preferred_common_name")
            )

            return result
        except requests.RequestException as e:
            print(f"Error fetching taxon {taxon_id}: {str(e)}")
            return None

    @staticmethod
    def get_user_observations(username: str, taxonomic_group: Optional[str] = None, per_page: int = 200) -> List[Dict]:
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
                            taxon_details = INaturalistAPI.get_taxon_details(taxon_id)
                            if not taxon_details:
                                time.sleep(0.5)  # Rate limiting

                        # Add ancestor details to the observation
                        obs["taxon"]["ancestors"] = [
                            INaturalistAPI.get_taxon_details(aid)
                            for aid in ancestor_ids
                            if INaturalistAPI.get_taxon_details(aid)
                        ]

                observations.extend(data["results"])

                # Debug print for first observation's ancestors (only on first page)
                if page == 1 and data["results"]:
                    first_obs = data["results"][0]
                    print("\nFirst observation ancestry:")
                    print(f"Taxon: {first_obs['taxon']['name']}")
                    print("Ancestors:")
                    for ancestor in first_obs["taxon"].get("ancestors", []):
                        print(f"  {ancestor['rank']}: {ancestor['name']}")

                if len(data["results"]) < per_page:
                    break

                page += 1
                time.sleep(1)  # Rate limiting

            except requests.RequestException as e:
                raise Exception(f"Error fetching observations: {str(e)}")

        return observations