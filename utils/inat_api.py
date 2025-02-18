import requests
from typing import Dict, List, Optional
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
        "Insects": 47158,    # Class Insecta
        "Fungi": 47170,      # Kingdom Fungi
        "Plants": 47126,     # Kingdom Plantae
        "Mammals": 40151,    # Class Mammalia
        "Reptiles": 26036,   # Class Reptilia
        "Amphibians": 20978, # Class Amphibia
        "Mollusks": 47115,    # Phylum Mollusca
        "Birds": 3,
        "Spiders":47118,
        "Fish": 47178
    }

    @staticmethod
    def get_taxon_details(taxon_id: int, include_ancestors: bool = False) -> Optional[Dict]:
        """
        Fetch detailed information about a specific taxon.
        This version uses only the 'ancestor_ids' field.
        """
        db = Database.get_instance()
        cached_data = db.get_cached_branch(taxon_id)
        if cached_data:
            print(f"Found cached data for taxon {taxon_id}")
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

            # We no longer use the full 'ancestors' field.
            # Instead, we use the API's own ancestor_ids (optionally you could normalize them)
            result["ancestor_ids"] = result.get("ancestor_ids", [])
            # Cache only the necessary fields
            db.save_branch(taxon_id, {
                "name": result.get("name", ""),
                "rank": result.get("rank", ""),
                "preferred_common_name": result.get("preferred_common_name", ""),
                "parent_id": result.get("ancestor_ids", [])[-1] if result.get("ancestor_ids") else None,
                "ancestor_ids": result.get("ancestor_ids", [])
            })
            return result
        except requests.RequestException as e:
            print(f"Error fetching taxon {taxon_id}: {str(e)}")
            return None

    @staticmethod
    def ensure_taxon_in_db(taxon_id: int) -> Optional[Dict]:
        """
        Ensure that a given taxon (and all its ancestors) are stored in the taxa table.
        Relies solely on 'ancestor_ids'.
        """
        db = Database.get_instance()
        cached = db.get_cached_branch(taxon_id)
        if cached and cached.get("ancestor_ids") is not None:
            return cached

        taxon_data = INaturalistAPI.get_taxon_details(taxon_id)
        if not taxon_data:
            print(f"Could not fetch taxon {taxon_id} from iNat")
            return None

        ancestors = taxon_data.get("ancestor_ids", [])
        parent_id = ancestors[-1] if ancestors else None

        record = {
            "name": taxon_data.get("name", ""),
            "rank": taxon_data.get("rank", ""),
            "preferred_common_name": taxon_data.get("preferred_common_name", ""),
            "parent_id": parent_id,
            "ancestor_ids": ancestors
        }
        db.save_branch(taxon_id, record)
        new_record = db.get_cached_branch(taxon_id)
        if not new_record:
            print(f"Warning: After saving, no record found for taxon {taxon_id}")
            return None

        print(f"[DEBUG] Saved record for taxon {taxon_id}: {new_record}")
        for aid in ancestors:
            INaturalistAPI.ensure_taxon_in_db(aid)
        return new_record

    @staticmethod
    def get_full_ancestor_chain(species_id: int) -> List[int]:
        """
        Returns a complete chain (from root to species) for the given species.
        This function uses only the 'ancestor_ids' field.
        """
        print(f"\nGetting ancestor chain for species {species_id}")
        record = INaturalistAPI.ensure_taxon_in_db(species_id)
        if not record:
            print(f"No record found for taxon {species_id}")
            return []
        chain = record.get("ancestor_ids", [])
        print(f"Initial chain for {species_id}: {chain}")
        # If the chain starts with our designated root (48460), remove it
        if chain and chain[0] == 48460:
            chain = chain[1:]
            print(f"Chain after skipping duplicate root: {chain}")
        print(f"Ensuring all ancestors are in DB for species {species_id}")
        for aid in chain:
            ancestor_record = INaturalistAPI.ensure_taxon_in_db(aid)
            if ancestor_record:
                print(f"  Ancestor {aid} record: ancestor_ids = {ancestor_record.get('ancestor_ids')}")
            else:
                print(f"  Warning: Could not ensure ancestor {aid}")
        final_chain = [48460] + chain + [species_id]
        print(f"Final chain for {species_id}: {final_chain}")
        return final_chain

    @staticmethod
    def merge_branches_into_tree(species_ids: List[int]) -> Dict:
        """
        Given a list of species IDs, builds (or updates) the overall tree
        by merging each species' ancestor chain.
        """
        print("\nMerging branches into tree...")
        tree = {
            "id": 48460,  # ROOT_ID for Life
            "name": "Life",
            "rank": "stateofmatter",
            "common_name": "Life",
            "children": {}
        }
        db = Database.get_instance()
        for species_id in species_ids:
            print(f"\nProcessing species {species_id}")
            chain = INaturalistAPI.get_full_ancestor_chain(species_id)
            print(f"Got ancestor chain: {chain}")
            current_node = tree
            for taxon_id in chain:
                key = str(taxon_id)
                record = db.get_cached_branch(taxon_id)
                if record:
                    print(f"[DEBUG] Found record for taxon {taxon_id}: {record}")
                    if key not in current_node["children"]:
                        current_node["children"][key] = {
                            "id": record["id"],
                            "name": record["name"],
                            "rank": record["rank"],
                            "common_name": record.get("common_name", ""),
                            "children": {}
                        }
                        print(f"Added node {key} to tree: {current_node['children'][key]}")
                    else:
                        print(f"Node {key} already exists in tree")
                else:
                    print(f"[DEBUG] No record found for taxon {taxon_id}")
                    print(f"Warning: Missing taxon record for {taxon_id}")
                    continue
                current_node = current_node["children"][key]
        print(f"\nFinal tree structure:")
        print(f"Root children count: {len(tree['children'])}")
        return tree

    @staticmethod
    def _get_ancestor_ids(rank: str, row: pd.Series) -> List[int]:
        """
        Helper method to construct ancestor IDs in order using only our ancestor_ids.
        """
        ancestor_ids = []
        ranks = ["stateofmatter", "kingdom", "phylum", "class", "order", "family", "genus", "species"]
        try:
            current_pos = ranks.index(rank)
        except ValueError:
            print(f"Warning: Unknown rank '{rank}'")
            return []
        for i in range(current_pos):
            ancestor_rank = ranks[i]
            if pd.notna(row.get(ancestor_rank)):
                ancestor_ids.append(int(row[ancestor_rank]))
        return ancestor_ids

    def get_user_observations(self, username: str, taxonomic_group: Optional[str] = None, per_page: int = 200) -> List[Dict]:
        """
        Fetch observations for a given iNaturalist username with optional taxonomic filtering.
        """
        observations = []
        page = 1
        db = Database.get_instance()
        taxonomy_cache = TaxonomyCache()
        root_taxon_id = None
        if taxonomic_group in self.taxon_params:
            root_taxon_id = self.taxon_params[taxonomic_group]
            print(f"Using taxonomic filter for {taxonomic_group} (ID: {root_taxon_id})")
            cached_tree = taxonomy_cache.get_cached_tree(root_taxon_id)
            if cached_tree and cached_tree.get('confidence_complete', False):
                print(f"Found complete cached tree for {taxonomic_group}")
                try:
                    species_ids = [id for id in cached_tree.get('ancestor_chain', [])
                                   if db.get_cached_branch(id) and db.get_cached_branch(id).get('rank') == 'species']
                    print(f"Found {len(species_ids)} species in cache")
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
                                    "ancestor_ids": species_data["ancestor_ids"]
                                }
                            }
                            observations.append(observation)
                    print(f"Reconstructed {len(observations)} observations from cache")
                    return observations
                except Exception as e:
                    print(f"Error reconstructing observations from cache: {e}")
        while True:
            try:
                params = {
                    "user_login": username,
                    "per_page": per_page,
                    "page": page,
                    "order": "desc",
                    "order_by": "created_at",
                    "quality_grade": "research",
                    "verifiable": "true",
                    "include_new_projects": "true",
                    "locale": "en",
                    "preferred_place_id": "1",
                    "include": ["taxon", "ancestors"]
                }
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
                for obs in data["results"]:
                    if "taxon" in obs:
                        taxon = obs["taxon"]
                        species_id = taxon["id"]
                        if taxon.get("rank") == "species":
                            ancestor_ids = taxon.get("ancestor_ids", [])
                            ancestors = []
                            if ancestor_ids:
                                cached_ancestors = taxonomy_cache.get_ancestors(species_id)
                                if cached_ancestors:
                                    ancestors = cached_ancestors
                                else:
                                    for aid in ancestor_ids:
                                        ancestor = self.get_taxon_details(aid)
                                        if ancestor:
                                            ancestors.append(ancestor)
                                            db.save_branch(aid, ancestor)
                                            time.sleep(0.5)  # Rate limiting
                            db.save_branch(species_id, {
                                "name": taxon["name"],
                                "rank": "species",
                                "preferred_common_name": taxon.get("preferred_common_name", ""),
                                "ancestor_ids": ancestor_ids
                            })
                            # We now only use the 'ancestor_ids' field, so we don't add full ancestors here.
                            obs["taxon"]["ancestor_ids"] = ancestor_ids
                    observations.append(obs)
                if len(data["results"]) < per_page:
                    break
                page += 1
                time.sleep(1)
            except requests.RequestException as e:
                print(f"API Error: {str(e)}")
                print(f"Response content: {e.response.content if hasattr(e, 'response') else 'No response content'}")
                raise Exception(f"Error fetching observations: {str(e)}")
        print(f"Total observations fetched: {len(observations)}")
        return observations

def build_and_cache_tree(username: str, taxonomic_group: str) -> Optional[Dict]:
    """
    Build and cache a complete taxonomic tree for a user and group.
    """
    api = INaturalistAPI()
    tree = api.process_observations(username, taxonomic_group)
    if not tree:
        print("Failed to build tree")
        return None
    taxonomy_cache = TaxonomyCache()
    root_id = INaturalistAPI.taxon_params.get(taxonomic_group, 48460)  # Default to Life
    cached_tree = taxonomy_cache.get_cached_tree(root_id)
    if cached_tree:
        print(f"Successfully cached tree for {taxonomic_group}")
        return cached_tree['tree']
    print("Warning: Tree was built but not cached")
    return tree
