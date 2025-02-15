import requests
from typing import Dict, List, Optional
import time
from utils.database import Database

class INaturalistAPI:
    BASE_URL = "https://api.inaturalist.org/v1"

    @staticmethod
    def get_taxon_details(taxon_id: int, include_ancestors: bool = False) -> Optional[Dict]:
        """Fetch detailed information about a specific taxon."""
        db = Database.get_instance()
        
        # Check for cached branch first if ancestors are needed
        if include_ancestors:
            cached_branch = db.get_cached_branch(taxon_id)
            if cached_branch:
                print(f"Found cached branch for taxon {taxon_id}")
                return cached_branch
        else:
            # Check for individual taxon cache
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
                    if "taxon" in obs:
                        taxon = obs["taxon"]
                        species_id = taxon["id"]
                        
                        # Try to get cached branch first
                        cached_branch = db.get_cached_branch(species_id)
                        if cached_branch:
                            obs["taxon"]["ancestors"] = cached_branch["ancestry"]
                            continue
                            
                        # If not cached, fetch and cache the full branch
                        if "ancestor_ids" in taxon:
                            ancestor_ids = taxon["ancestor_ids"]
                            ancestors = []
                            
                            for aid in ancestor_ids:
                                ancestor = INaturalistAPI.get_taxon_details(aid)
                                if ancestor:
                                    ancestors.append(ancestor)
                                    time.sleep(0.5)  # Rate limiting
                            
                            # Cache the branch
                            branch_data = {
                                "name": taxon["name"],
                                "ancestry": ancestors
                            }
                            db.save_branch(species_id, branch_data)
                            obs["taxon"]["ancestors"] = ancestors

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