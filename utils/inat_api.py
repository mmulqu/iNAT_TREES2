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
        "Insects": 47158,  # Class Insecta
        "Fungi": 47170,  # Kingdom Fungi
        "Plants": 47126,  # Kingdom Plantae
        "Mammals": 40151,  # Class Mammalia
        "Reptiles": 26036,  # Class Reptilia
        "Amphibians": 20978,  # Class Amphibia
        "Mollusks": 47115 # Phylum Mollusca
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
    def process_observations(username: str, taxonomic_group: str):
        """Process observations and build taxonomy tree."""
        from utils.database import Database
        from utils.taxonomy_cache import TaxonomyCache

        print("\n=== Starting process_observations ===")
        print(f"Username: {username}")
        print(f"Taxonomic group: {taxonomic_group}")

        # Get the appropriate root ID for the taxonomic group first
        root_id = INaturalistAPI.taxon_params.get(taxonomic_group)
        if not root_id:
            print(f"ERROR: No root_id found for taxonomic group: {taxonomic_group}")
            return None

        # Check if we have a cached tree
        taxonomy_cache = TaxonomyCache()
        cached_tree = taxonomy_cache.get_cached_tree(root_id)
        if cached_tree:
            print(f"Found cached tree for {taxonomic_group}")
            return cached_tree['tree']

        # If no cache, fetch and process observations
        api = INaturalistAPI()
        observations = api.get_user_observations(username, taxonomic_group)
        print(f"\nFetched {len(observations)} observations")

        # Collect all taxa data
        taxa_data = []
        db = Database.get_instance()

        print("\nProcessing observations...")
        for obs in observations:
            if 'taxon' in obs:
                taxon = obs['taxon']
                print(f"\nProcessing taxon: {taxon.get('name')} (ID: {taxon.get('id')})")

                # Debug print ancestor_ids
                print(f"Ancestor IDs: {taxon.get('ancestor_ids')}")

                taxa_data.append({
                    'taxon_id': taxon['id'],
                    'name': taxon['name'],
                    'rank': taxon['rank'],
                    'ancestor_ids': taxon.get('ancestor_ids', [])
                })

                # Also add ancestors to taxa data
                if 'ancestors' in taxon:
                    print(f"Processing {len(taxon['ancestors'])} ancestors")
                    for ancestor in taxon['ancestors']:
                        print(f"  Adding ancestor: {ancestor.get('name')} (ID: {ancestor.get('id')})")
                        taxa_data.append({
                            'taxon_id': ancestor['id'],
                            'name': ancestor['name'],
                            'rank': ancestor['rank'],
                            'ancestor_ids': ancestor.get('ancestor_ids', [])
                        })
                else:
                    print("No ancestors found in taxon data")

        # Remove duplicates
        print("\nRemoving duplicates...")
        df = pd.DataFrame(taxa_data).drop_duplicates(subset=['taxon_id'])
        print(f"Unique taxa count: {len(df)}")

        # Debug print data before tree building
        print("\nData for tree building:")
        print(df[['taxon_id', 'name', 'rank', 'ancestor_ids']].head())

        # Build the tree
        print("\nBuilding taxonomy tree...")
        builder = TreeBuilder()
        complete_tree = builder.build_taxonomy_tree(df.to_dict('records'))

        if complete_tree is None:
            print("ERROR: complete_tree is None after building!")
            return None

        print(f"\nLooking for root node with ID: {root_id}")
        # Extract the subtree for our taxonomic group
        group_tree = builder.find_root_node(complete_tree, root_id)
        if not group_tree:
            print(f"ERROR: Could not find root node with ID: {root_id}")
            return None

        # Get all taxa IDs and species IDs
        print("\nCollecting taxa IDs...")
        all_taxa = builder.collect_all_taxa_ids(group_tree)
        print(f"Found {len(all_taxa)} total taxa")

        species_ids = [
            tid for tid in all_taxa
            if df[df['taxon_id'] == tid]['rank'].iloc[0] == 'species'
        ]
        print(f"Found {len(species_ids)} species")

        # Save to cache
        print("\nSaving to taxonomy cache...")
        taxonomy_cache.save_tree(
            root_id=root_id,
            tree=group_tree,
            species_ids=species_ids
        )

        print("=== Finished process_observations ===\n")
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

            # Check if we have a cached tree for this taxonomic group
            cached_tree = taxonomy_cache.get_cached_tree(root_taxon_id)
            if cached_tree:
                print(f"Found cached tree for {taxonomic_group}")
                return []  # Return empty list to skip API calls since we have cached data

        while True:
            try:
                # Base parameters
                params = {
                    "user_login": username,
                    "per_page": per_page,
                    "page": page,
                    "order": "desc",
                    "order_by": "created_at",
                    "include": ["taxon", "ancestors"]
                }

                # Add taxonomic filter if specified
                if root_taxon_id:
                    params["taxon_id"] = root_taxon_id

                print(f"Making API request with params: {params}")

                response = requests.get(
                    f"{self.BASE_URL}/observations",
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

                            # Check cache before fetching ancestors
                            cached_ancestors = taxonomy_cache.get_ancestors(species_id)
                            if cached_ancestors:
                                ancestors = cached_ancestors
                            else:
                                # Fetch and cache each ancestor's details
                                for aid in ancestor_ids:
                                    ancestor = self.get_taxon_details(aid)
                                    if ancestor:
                                        ancestors.append(ancestor)
                                        time.sleep(0.5)  # Rate limiting

                            # Save the species with complete information
                            db.save_branch(species_id, {
                                "name": taxon["name"],
                                "rank": "species",
                                "preferred_common_name": taxon.get("preferred_common_name", ""),
                                "ancestor_ids": ancestor_ids,
                                "ancestor_data": ancestors
                            })

                            # Update the observation with complete ancestor information
                            obs["taxon"]["ancestors"] = ancestors

                observations.extend(data["results"])

                if len(data["results"]) < per_page:
                    break

                page += 1
                time.sleep(1)  # Rate limiting

            except requests.RequestException as e:
                print(f"API Error: {str(e)}")
                print(f"Response content: {e.response.content if hasattr(e, 'response') else 'No response content'}")
                raise Exception(f"Error fetching observations: {str(e)}")

        return observations