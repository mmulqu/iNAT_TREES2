import requests
from typing import Dict, List, Optional, Set
import time
from utils.taxonomy_cache import TaxonomyCache
from utils.tree_builder import TreeBuilder
from utils.database import Database
import pandas as pd
from utils.data_utils import normalize_ancestors

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
        "Mollusks": 47115  # Phylum Mollusca
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
                return {
                    "id": taxon_id,
                    "name": cached_data["name"],
                    "rank": cached_data["rank"],
                    "preferred_common_name": cached_data["common_name"],
                    "ancestor_ids": cached_data["ancestor_ids"],
                    "ancestors": cached_data["ancestors"]
                }
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

            # Normalize ancestors right away
            result["ancestors"] = normalize_ancestors(result.get("ancestors", []))

            # Cache the result (this will only insert if not already cached)
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
        from utils.data_processor import DataProcessor

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

        if not observations:
            print("No observations to process.")
            return None

        # Process the observations to get structured data
        df = DataProcessor.process_observations(observations, taxonomic_group)
        if df.empty:
            print("No valid observations after processing.")
            return None

        # Get taxa data from processed observations
        taxa_data = []
        for _, row in df.iterrows():
            # Process each taxon in the hierarchy
            for rank in ["stateofmatter"] + DataProcessor.TAXONOMIC_RANKS:
                if pd.notna(row.get(rank)):
                    taxon_id = int(row[rank])
                    taxa_data.append({
                        'taxon_id': taxon_id,
                        'name': row.get(f"taxon_{rank}", ""),
                        'rank': rank,
                        'ancestor_ids': INaturalistAPI._get_ancestor_ids(rank, row)
                    })

        # Remove duplicates
        unique_taxa = {}
        for taxon in taxa_data:
            if taxon['taxon_id'] not in unique_taxa:
                unique_taxa[taxon['taxon_id']] = taxon

        unique_taxa_list = list(unique_taxa.values())
        print(f"\nUnique taxa count: {len(unique_taxa_list)}")

        if not unique_taxa_list:
            print("No taxa data to build tree from.")
            return None

        # Debug print data before tree building
        print("\nData for tree building:")
        sample_data = unique_taxa_list[:min(5, len(unique_taxa_list))]
        for taxon in sample_data:
            print(f"ID: {taxon['taxon_id']}, Name: {taxon['name']}, Rank: {taxon['rank']}, Ancestors: {taxon['ancestor_ids']}")

        # Build the tree
        print("\nBuilding taxonomy tree...")
        builder = TreeBuilder()
        complete_tree = builder.build_taxonomy_tree(unique_taxa_list)

        if complete_tree is None:
            print("ERROR: complete_tree is None after building!")
            return None

        print(f"\nLooking for root node with ID: {root_id}")
        # Extract the subtree for our taxonomic group
        group_tree = builder.find_root_node(complete_tree, root_id)
        if not group_tree:
            print(f"ERROR: Could not find root node with ID: {root_id}")
            group_tree = complete_tree  # Use complete tree if root node not found

        # Get all taxa IDs and species IDs
        print("\nCollecting taxa IDs...")
        all_taxa = builder.collect_all_taxa_ids(group_tree)
        print(f"Found {len(all_taxa)} total taxa")

        species_ids = []
        for taxon_id in all_taxa:
            taxon_data = next((t for t in unique_taxa_list if t['taxon_id'] == taxon_id), None)
            if taxon_data and taxon_data['rank'] == 'species':
                species_ids.append(taxon_id)

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

    @staticmethod
    def _get_ancestor_ids(rank: str, row: pd.Series) -> List[int]:
        """Helper method to construct ancestor IDs in order."""
        ancestor_ids = []

        # Define the ordering of taxonomic ranks
        ranks = ["stateofmatter", "kingdom", "phylum", "class", "order", "family", "genus", "species"]

        # Find the position of the current rank
        try:
            current_pos = ranks.index(rank)
        except ValueError:
            print(f"Warning: Unknown rank '{rank}'")
            return []

        # Add all ancestors in order
        for i in range(current_pos):
            ancestor_rank = ranks[i]
            if pd.notna(row.get(ancestor_rank)):
                ancestor_ids.append(int(row[ancestor_rank]))

        return ancestor_ids

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
            if cached_tree and cached_tree.get('confidence_complete', False):
                print(f"Found complete cached tree for {taxonomic_group}")
                try:
                    # Get species IDs from ancestor chain
                    species_ids = [id for id in cached_tree.get('ancestor_chain', []) 
                                 if db.get_cached_branch(id) and 
                                 db.get_cached_branch(id).get('rank') == 'species']

                    print(f"Found {len(species_ids)} species in cache")

                    # Reconstruct observations from cached data
                    for species_id in species_ids:
                        species_data = db.get_cached_branch(species_id)
                        if species_data:
                            observation = {
                                "id": f"cached_{species_id}",
                                "taxon": {
                                    "id": species_id,
                                    "name": species_data["name"],
                                    "rank": "species",
                                    "preferred_common_name": species_data["common_name"],
                                    "ancestor_ids": species_data["ancestor_ids"],
                                    "ancestors": species_data["ancestors"]
                                }
                            }
                            observations.append(observation)

                    print(f"Reconstructed {len(observations)} observations from cache")
                    return observations
                except Exception as e:
                    print(f"Error reconstructing observations from cache: {e}")
                    # Continue with API call if reconstruction fails

        while True:
            try:
                # Base parameters
                params = {
                    "user_login": username,
                    "per_page": per_page,
                    "page": page,
                    "order": "desc",
                    "order_by": "created_at",
                    "quality_grade": "research",  # Add this to ensure we get verified observations
                    "verifiable": "true",         # Add this to get verifiable observations
                    "include_new_projects": "true", # Include observations from new projects
                    "locale": "en",               # Set locale to English
                    "preferred_place_id": "1",    # Global
                    "include": ["taxon", "ancestors"]
                }

                # Add taxonomic filter if specified
                if root_taxon_id:
                    params["taxon_id"] = root_taxon_id

                print(f"Making API request with params: {params}")

                response = requests.get(
                    f"{self.BASE_URL}/observations",
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json"
                    }
                )
                response.raise_for_status()
                data = response.json()

                print(f"API Response status: {response.status_code}")
                print(f"Total results: {data.get('total_results', 0)}")
                print(f"Results in this page: {len(data.get('results', []))}")

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

                            # Store the species to ancestor relationship
                            if ancestor_ids:
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
                                            # Save the ancestor in the DB
                                            db.save_branch(aid, ancestor)
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

        print(f"Total observations fetched: {len(observations)}")
        return observations

    def _cache_species_ancestors(self, species_maps: Dict[int, List[int]], root_id: Optional[int] = None):
        """Cache species to ancestor relationships."""
        taxonomy_cache = TaxonomyCache()

        for species_id, ancestor_ids in species_maps.items():
            # Save to species_ancestors table
            try:
                with taxonomy_cache.conn:
                    with taxonomy_cache.conn.cursor() as cur:
                        # Add the species itself to the ancestor chain
                        full_chain = ancestor_ids + [species_id]

                        cur.execute("""
                            INSERT INTO species_ancestors 
                            (species_id, root_id, ancestor_chain, last_updated)
                            VALUES (%s, %s, %s, NOW())
                            ON CONFLICT (species_id, root_id) DO UPDATE
                            SET ancestor_chain = EXCLUDED.ancestor_chain,
                                last_updated = NOW()
                        """, (
                            species_id,
                            root_id if root_id else 48460,  # Use Life as default root
                            full_chain
                        ))
                print(f"Cached ancestor chain for species {species_id}")
            except Exception as e:
                print(f"Error caching species ancestors: {e}")


def build_and_cache_tree(username: str, taxonomic_group: str) -> Optional[Dict]:
    """Build and cache a complete taxonomic tree for a user and group."""
    api = INaturalistAPI()

    # Process the observations to build the tree
    tree = api.process_observations(username, taxonomic_group)
    if not tree:
        print("Failed to build tree")
        return None

    # Verify the tree was successfully cached
    taxonomy_cache = TaxonomyCache()
    root_id = INaturalistAPI.taxon_params.get(taxonomic_group, 48460)  # Default to Life

    cached_tree = taxonomy_cache.get_cached_tree(root_id)
    if cached_tree:
        print(f"Successfully cached tree for {taxonomic_group}")
        return cached_tree['tree']

    print("Warning: Tree was built but not cached")
    return tree