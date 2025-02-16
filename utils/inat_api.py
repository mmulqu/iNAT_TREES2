import requests
from typing import Dict, List, Optional
import time
from utils.taxonomy_cache import TaxonomyCache

from utils.tree_builder import TreeBuilder
import pandas as pd

class INaturalistAPI:
    BASE_URL = "https://api.inaturalist.org/v1"
    
    # Taxonomic group IDs
    taxon_params = {
        "Insects": 47158,     # Class Insecta
        "Fungi": 47170,       # Kingdom Fungi
        "Plants": 47126,      # Kingdom Plantae
        "Mammals": 40151,     # Class Mammalia
        "Reptiles": 26036,    # Class Reptilia
        "Amphibians": 20978   # Class Amphibia
    }

    @staticmethod
    def get_taxon_details(taxon_id: int, include_ancestors: bool = False) -> Optional[Dict]:
        """Fetch detailed information about a specific taxon."""
        from utils.database import Database  # Import here to avoid circular dependency

        db = Database.get_instance()
        cached_data = db.get_cached_branch(taxon_id)
        if cached_data:
            print(f"Found cached data for taxon {taxon_id}")
            if include_ancestors:
                return cached_data["ancestor_data"]
            return {
                "id": taxon_id,
                "name": cached_data["name"],
                "rank": cached_data["rank"],
                "preferred_common_name": cached_data["common_name"],
                "ancestor_ids": cached_data["ancestor_ids"]
            }

        try:
            print(f"Fetching taxon {taxon_id} from API")
            response = requests.get(f"{INaturalistAPI.BASE_URL}/taxa/{taxon_id}")
            response.raise_for_status()
            result = response.json()["results"][0]

            # Cache the result
            db.save_branch(taxon_id, result)

            return result
        except requests.RequestException as e:
            print(f"Error fetching taxon {taxon_id}: {str(e)}")
            return None

    @staticmethod
    @staticmethod
    def process_observations(username: str, taxonomic_group: str):
        """Process observations and build taxonomy tree."""
        from utils.database import Database
        from utils.taxonomy_cache import TaxonomyCache
        
        # Get observations from iNaturalist
        api = INaturalistAPI()
        observations = api.get_user_observations(username, taxonomic_group)
        
        # Collect all taxa data
        taxa_data = []
        db = Database.get_instance()
        
        for obs in observations:
            if 'taxon' in obs:
                taxon = obs['taxon']
                taxa_data.append({
                    'taxon_id': taxon['id'],
                    'name': taxon['name'],
                    'rank': taxon['rank'],
                    'ancestor_ids': taxon.get('ancestor_ids', [])
                })
                
                # Also add ancestors to taxa data
                for ancestor in taxon.get('ancestors', []):
                    taxa_data.append({
                        'taxon_id': ancestor['id'],
                        'name': ancestor['name'],
                        'rank': ancestor['rank'],
                        'ancestor_ids': ancestor.get('ancestor_ids', [])
                    })
        
        # Remove duplicates
        df = pd.DataFrame(taxa_data).drop_duplicates(subset=['taxon_id'])
        
        # Build the tree
        builder = TreeBuilder()
        complete_tree = builder.build_taxonomy_tree(df.to_dict('records'))
        
        # Get the appropriate root ID for the taxonomic group
        root_id = INaturalistAPI.taxon_params.get(taxonomic_group)
        if not root_id:
            return None
            
        # Extract the subtree for our taxonomic group
        group_tree = builder.find_root_node(complete_tree, root_id)
        if not group_tree:
            return None
            
        # Get all taxa IDs and species IDs
        all_taxa = builder.collect_all_taxa_ids(group_tree)
        species_ids = [
            tid for tid in all_taxa 
            if df[df['taxon_id'] == tid]['rank'].iloc[0] == 'species'
        ]
        
        # Save to cache
        taxonomy_cache = TaxonomyCache()
        taxonomy_cache.save_tree(
            root_id=root_id,
            tree=group_tree,
            species_ids=species_ids
        )
        
        return group_tree

    def get_user_observations(self, username: str, taxonomic_group: Optional[str] = None, per_page: int = 200) -> List[Dict]:
        """Fetch observations for a given iNaturalist username with optional taxonomic filtering."""
        from utils.database import Database
        
        observations = []
        page = 1
        db = Database.get_instance()
        taxonomy_cache = TaxonomyCache()

        # Get root taxon ID if taxonomic group is specified
        root_taxon_id = None
        if taxonomic_group in self.taxon_params:
            root_taxon_id = self.taxon_params[taxonomic_group]
            print(f"Using taxonomic filter for {taxonomic_group} (ID: {root_taxon_id})")

        while True:
            try:
                # Base parameters
                params = {
                    "user_login": username,
                    "per_page": per_page,
                    "page": page,
                    "order": "desc",
                    "order_by": "created_at",
                    "include_taxon": "true",
                    "include_ancestors": "true"
                }

                # Add taxonomic filter if specified
                if root_taxon_id:
                    params["taxon_id"] = root_taxon_id

                print(f"Making API request with params: {params}")

                print(f"Making API request with params: {params}")

                response = requests.get(
                    f"{INaturalistAPI.BASE_URL}/observations",
                    params=params
                )
                response.raise_for_status()
                data = response.json()

                if not data["results"]:
                    break

                # Process observations and build taxonomy
                for obs in data["results"]:
                    if "taxon" in obs:
                        taxon = obs["taxon"]
                        species_id = taxon["id"]

                        # Make sure we have all the data for species level taxa
                        if taxon.get("rank") == "species":
                            ancestor_ids = taxon.get("ancestor_ids", [])
                            ancestors = []

                            # Fetch and cache each ancestor's details
                            for aid in ancestor_ids:
                                ancestor = INaturalistAPI.get_taxon_details(aid)
                                if ancestor:
                                    ancestors.append(ancestor)
                                    time.sleep(0.5)  # Rate limiting

                            # Save the species with complete information
                            db.save_branch(species_id, {
                                "name": taxon["name"],
                                "rank": "species",  # Explicitly set species rank
                                "preferred_common_name": taxon.get("preferred_common_name", ""),
                                "ancestor_ids": ancestor_ids,  # Include full ancestry chain
                                "ancestor_data": ancestors  # Store complete ancestor information
                            })

                            # Update the observation with complete ancestor information
                            obs["taxon"]["ancestors"] = ancestors

                            # If we're building a complete taxonomy, update it
                            if root_taxon_id and root_taxon_id in ancestor_ids:
                                current_tree = taxonomy_cache.get_cached_tree(root_taxon_id) or {}
                                # Add this species and its lineage to the tree
                                # This will be handled by the TaxonomyCache class

                observations.extend(data["results"])

                if len(data["results"]) < per_page:
                    break

                page += 1
                time.sleep(1)  # Rate limiting

            except requests.RequestException as e:
                raise Exception(f"Error fetching observations: {str(e)}")

        return observations