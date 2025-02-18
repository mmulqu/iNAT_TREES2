import pandas as pd
from typing import List, Dict, Optional, Union, Any, Set, Tuple
from utils.taxonomy_cache import TaxonomyCache
from utils.database import Database
from utils.data_utils import normalize_ancestors
from utils.inat_api import INaturalistAPI  # Import INaturalistAPI directly

class DataProcessor:
    TAXONOMIC_FILTERS = {
        "Insects": {"class": "Insecta", "id": 47158},
        "Fungi": {"kingdom": "Fungi", "id": 47170},
        "Plants": {"kingdom": "Plantae", "id": 47126},
        "Mammals": {"class": "Mammalia", "id": 40151},
        "Reptiles": {"class": "Reptilia", "id": 26036},
        "Amphibians": {"class": "Amphibia", "id": 20978},
        "Mollusks": {"phylum": "Mollusca", "id": 47115}
    }

    TAXONOMIC_RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    FULL_RANKS = ["stateofmatter"] + TAXONOMIC_RANKS

    @staticmethod
    def get_ancestor_name(ancestors: List[Dict], rank: str) -> str:
        """Extract ancestor name by rank from ancestors list."""
        for ancestor in ancestors:
            if isinstance(ancestor, dict) and ancestor.get("rank") == rank:
                return ancestor.get("name", "")
        return ""

    @staticmethod
    def process_ancestor_data(ancestor: Union[Dict, str], ancestor_data: Optional[Dict] = None) -> Dict[str, Any]:
        """Process ancestor data in either string or dictionary format."""
        if isinstance(ancestor, dict):
            return {
                "rank": ancestor.get("rank", ""),
                "name": ancestor.get("name", ""),
                "id": ancestor.get("id")
            }
        elif isinstance(ancestor, str) and ancestor_data:
            return {
                "rank": ancestor_data.get("rank", ""),
                "name": ancestor_data.get("name", ""),
                "id": ancestor_data.get("id")
            }
        return {"rank": "", "name": "", "id": None}

    @staticmethod
    def process_observations(observations: List[Dict], taxonomic_group: Optional[str] = None) -> pd.DataFrame:
        """Process raw observations into a structured DataFrame."""
        if not observations:
            print("No observations to process")
            return pd.DataFrame()

        print("\nProcessing observations...")
        print(f"Total observations: {len(observations)}")

        processed_data = []
        skipped_count = 0

        for obs in observations:
            try:
                if not obs.get("taxon") or not obs.get("id"):
                    skipped_count += 1
                    continue

                # Ensure taxon and its ancestors are in DB
                species_id = obs["taxon"]["id"]
                # Ensure the species and (recursively) its ancestors are in the database.
                record = INaturalistAPI.ensure_taxon_in_db(species_id)
                if not record:
                    print(f"Warning: Could not ensure taxon {species_id} in DB")

                taxon = obs["taxon"]

                # Normalize ancestor data immediately
                ancestors = normalize_ancestors(taxon.get("ancestors", {}))

                # Extract and process ancestor IDs
                ancestor_ids = []
                if taxon.get('ancestor_ids'):
                    if isinstance(taxon['ancestor_ids'], str):
                        try:
                            ancestor_ids = eval(taxon['ancestor_ids'])
                        except:
                            print(f"Could not parse ancestor_ids string: {taxon['ancestor_ids']}")
                    else:
                        ancestor_ids = taxon['ancestor_ids']

                # Print first observation's ancestor chain for debugging
                if len(processed_data) == 0:
                    print("\nFirst observation ancestors:")
                    print(f"Taxon: {taxon.get('name', 'Unknown')} (ID: {taxon.get('id')})")
                    print(f"Taxon rank: {taxon.get('rank')}")
                    print("Ancestors:")
                    print(f"  stateofmatter: Life (ID: 48460)")  # Add Life as root
                    for ancestor in ancestors:
                        rank = ancestor.get('rank', 'unknown')
                        name = ancestor.get('name', 'unknown')
                        aid = ancestor.get('id', 'unknown')
                        print(f"  {rank}: {name} (ID: {aid})")

                # Create mappings for both IDs and names
                ancestor_names = {}
                ancestor_ids_by_rank = {}

                # Add Life as the root
                ancestor_names["stateofmatter"] = "Life"
                ancestor_ids_by_rank["stateofmatter"] = 48460

                # Process ancestors and build complete taxonomy mapping
                for ancestor in ancestors:
                    rank = ancestor.get('rank', '')
                    if rank:
                        ancestor_names[rank] = ancestor.get('name', '')
                        ancestor_ids_by_rank[rank] = ancestor.get('id')

                # Fill in missing ranks from ancestor_ids if available
                if ancestor_ids:
                    db = Database.get_instance()
                    for aid in ancestor_ids:
                        try:
                            aid_int = int(aid)
                            if aid_int not in ancestor_ids_by_rank.values():
                                cached_data = db.get_cached_branch(aid_int)
                                if cached_data:
                                    rank = cached_data.get('rank', '')
                                    if rank and rank not in ancestor_ids_by_rank:
                                        ancestor_names[rank] = cached_data.get('name', '')
                                        ancestor_ids_by_rank[rank] = aid_int
                        except ValueError:
                            print(f"Invalid ancestor ID: {aid}")

                # Check for missing standard ranks
                std_ranks = {"kingdom", "phylum", "class", "order", "family", "genus"}
                missing_ranks = std_ranks - set(ancestor_ids_by_rank.keys())
                if missing_ranks and len(processed_data) == 0:
                    print(f"Warning: Missing taxonomic ranks: {missing_ranks}")

                # Create observation data
                processed_observation = {
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon.get("name", ""),
                    "rank": taxon.get("rank", ""),
                    "common_name": taxon.get("preferred_common_name", ""),
                    "observed_on": obs.get("observed_on"),
                    "photo_url": obs.get("photos", [{}])[0].get("url", ""),
                    "stateofmatter": 48460,  # Add Life
                    "taxon_stateofmatter": "Life"  # Add Life name
                }

                # Add rank-specific fields
                for rank in DataProcessor.TAXONOMIC_RANKS:
                    processed_observation[rank] = ancestor_ids_by_rank.get(rank)
                    processed_observation[f"taxon_{rank}"] = ancestor_names.get(rank, "")

                if taxon.get("rank") == "species":
                    processed_observation["species"] = taxon["id"]
                    processed_observation["taxon_species"] = taxon["name"]

                if taxonomic_group and taxonomic_group in DataProcessor.TAXONOMIC_FILTERS:
                    filter_info = DataProcessor.TAXONOMIC_FILTERS[taxonomic_group]
                    filter_rank = next(iter(filter_info.keys()))
                    filter_id = filter_info["id"]
                    processed_observation[filter_rank] = filter_id
                    processed_observation[f"taxon_{filter_rank}"] = taxonomic_group

                processed_data.append(processed_observation)

            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                skipped_count += 1
                continue

        print(f"\nProcessed {len(processed_data)} observations")
        if skipped_count > 0:
            print(f"Skipped {skipped_count} invalid observations")

        return pd.DataFrame(processed_data)

    @staticmethod
    def get_full_ancestor_chain(species_id: int) -> List[int]:
        """
        Returns a complete chain (from root to species) for the given species.
        It recursively ensures that each taxon in the chain exists in the DB.
        """
        print(f"\nGetting ancestor chain for species {species_id}")
        DataProcessor.debug_taxon_record(species_id)
        record = INaturalistAPI.ensure_taxon_in_db(species_id)
        if not record:
            print(f"No record found for taxon {species_id}")
            return []
        print(f"Taxon {species_id} record: ancestor_ids = {record.get('ancestor_ids')}")
        chain = record.get("ancestor_ids", [])
        print(f"Initial chain for {species_id}: {chain}")
        if chain and chain[0] == 48460:  # ROOT_ID
            chain = chain[1:]
            print(f"Chain after skipping duplicate root: {chain}")
        print(f"Ensuring all ancestors are in DB for {species_id}")
        for aid in chain:
            DataProcessor.debug_taxon_record(aid)
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
        Given a list of species IDs, build (or update) the overall tree by merging each species' ancestor chain.
        """
        print("\nMerging branches into tree...")
        tree = {
            "id": 48460,
            "name": "Life",
            "rank": "stateofmatter",
            "common_name": "Life",
            "children": {}
        }
        db = Database.get_instance()

        for species_id in species_ids:
            print(f"\nProcessing species {species_id}")
            chain = DataProcessor.get_full_ancestor_chain(species_id)
            print(f"Got ancestor chain: {chain}")
            current_node = tree
            for taxon_id in chain:
                key = str(taxon_id)
                if key not in current_node["children"]:
                    record = db.get_cached_branch(taxon_id)
                    if record:
                        print(f"[DEBUG] Found record for taxon {taxon_id}: {record}")
                        current_node["children"][key] = {
                            "id": record["id"],
                            "name": record["name"],
                            "rank": record["rank"],
                            "common_name": record.get("common_name", ""),
                            "children": {}
                        }
                        print(f"Added node {key} to tree: {current_node['children'][key]}")
                    else:
                        print(f"[DEBUG] No record found for taxon {taxon_id}")
                        print(f"Warning: Missing taxon record for {taxon_id}")
                        continue
                else:
                    print(f"Node {key} already exists in tree")
                current_node = current_node["children"][key]
        print(f"\nFinal tree structure:")
        print(f"Root children count: {len(tree['children'])}")
        return tree

    @staticmethod
    def build_taxonomy_hierarchy(df: pd.DataFrame, taxonomic_group: Optional[str] = None) -> Dict:
        """
        For each unique species in df, retrieve its ancestor chain from the DB (fetching missing taxa as needed)
        and merge these chains into one tree.
        """
        if df.empty:
            print("No data to build hierarchy from")
            return {}

        print("\nBuilding taxonomy hierarchy...")
        print(f"Processing {len(df)} observations")
        root_id = None
        if taxonomic_group:
            root_id = DataProcessor.TAXONOMIC_FILTERS.get(taxonomic_group, {}).get("id")
            print(f"Using root ID {root_id} for {taxonomic_group}")
            taxonomy_cache = TaxonomyCache()
            if root_id:
                cached_tree = taxonomy_cache.get_cached_tree(root_id)
                if cached_tree:
                    print("Using cached complete tree")
                    return cached_tree

        species_ids = list(set(df["taxon_id"].tolist()))
        print(f"Found {len(species_ids)} unique species")
        tree = DataProcessor.merge_branches_into_tree(species_ids)

        if root_id:
            try:
                taxonomy_cache = TaxonomyCache()
                taxonomy_cache.save_tree(root_id=root_id, tree=tree)
            except Exception as e:
                print(f"Failed to save tree to cache: {e}")

        return tree

    @staticmethod
    def create_node(taxon_id: int, name: str, rank: str, common_name: str = "") -> Dict:
        """Create a properly structured node dictionary."""
        return {
            "id": taxon_id,
            "name": name,
            "rank": rank,
            "common_name": common_name,
            "children": {}
        }

    @staticmethod
    def _build_complete_tree(df: pd.DataFrame, taxonomic_group: Optional[str] = None) -> Dict:
        """Build a complete tree directly from observation data."""
        print("\nBuilding complete taxonomy tree...")
        tree = DataProcessor.create_node(
            taxon_id=48460,
            name="Life",
            rank="stateofmatter"
        )
        ranks = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
        taxa_by_rank = {rank: {} for rank in ranks}
        parent_child_map = {}

        for _, row in df.iterrows():
            prev_id = 48460
            for rank in ranks:
                taxon_id = row.get(rank)
                if pd.notna(taxon_id):
                    taxon_id = int(taxon_id)
                    if taxon_id not in taxa_by_rank[rank]:
                        taxa_by_rank[rank][taxon_id] = DataProcessor.create_node(
                            taxon_id=taxon_id,
                            name=row.get(f"taxon_{rank}", ""),
                            rank=rank,
                            common_name=row.get("common_name", "") if rank == "species" else ""
                        )
                    parent_child_map[taxon_id] = prev_id
                    prev_id = taxon_id

        def add_to_tree(node_id: int, parent_node: Dict) -> None:
            children = [tid for tid, pid in parent_child_map.items() if pid == node_id]
            for child_id in children:
                child_data = None
                for rank_data in taxa_by_rank.values():
                    if child_id in rank_data:
                        child_data = rank_data[child_id]
                        break
                if child_data:
                    parent_node["children"][str(child_id)] = child_data
                    add_to_tree(child_id, child_data)

        add_to_tree(48460, tree)
        return tree

    @staticmethod
    def _build_tree_from_dataframe(df: pd.DataFrame) -> Dict:
        """Build taxonomy tree directly from DataFrame."""
        print("\nBuilding tree from DataFrame...")
        print(f"Processing {len(df)} rows")
        print("\nDataFrame columns:", df.columns.tolist())
        if not df.empty:
            sample_row = df.iloc[0]
            for rank in ["stateofmatter"] + DataProcessor.TAXONOMIC_RANKS:
                print(f"{rank}: {sample_row.get(rank)}")
                print(f"taxon_{rank}: {sample_row.get(f'taxon_{rank}')}")
        taxa_info = {}
        root = {
            "id": 48460,
            "name": "Life",
            "rank": "stateofmatter",
            "common_name": "",
            "children": {}
        }
        for _, row in df.iterrows():
            for rank in DataProcessor.TAXONOMIC_RANKS:
                if pd.notna(row.get(rank)):
                    taxon_id = int(row[rank])
                    if taxon_id not in taxa_info:
                        if rank == "species":
                            name = row["name"]
                            common_name = row["common_name"]
                        else:
                            name = row[f"taxon_{rank}"]
                            common_name = ""
                        print(f"Adding taxon to info - ID: {taxon_id}, Rank: {rank}, Name: {name}")
                        taxa_info[taxon_id] = {
                            "id": taxon_id,
                            "name": name,
                            "common_name": common_name,
                            "rank": rank,
                            "children": {}
                        }
            if pd.notna(row.get("taxon_id")) and row.get("rank") not in DataProcessor.TAXONOMIC_RANKS:
                taxon_id = int(row["taxon_id"])
                if taxon_id not in taxa_info:
                    taxa_info[taxon_id] = {
                        "id": taxon_id,
                        "name": row["name"],
                        "common_name": row["common_name"],
                        "rank": row["rank"],
                        "children": {}
                    }
                    print(f"Adding observation taxon - ID: {taxon_id}, Rank: {row['rank']}, Name: {row['name']}")
        print(f"\nCollected {len(taxa_info)} unique taxa")
        for _, row in df.iterrows():
            current_level = root["children"]
            path = []
            for rank in DataProcessor.TAXONOMIC_RANKS:
                if pd.notna(row.get(rank)):
                    path.append((rank, int(row[rank])))
            if path:
                for i, (rank, taxon_id) in enumerate(path):
                    str_id = str(taxon_id)
                    if str_id not in current_level and taxon_id in taxa_info:
                        print(f"Adding node to tree - ID: {taxon_id}, Rank: {rank}")
                        current_level[str_id] = taxa_info[taxon_id].copy()
                    if i < len(path) - 1 and str_id in current_level:
                        current_level = current_level[str_id]["children"]
        print(f"\nFinal tree structure summary:")
        print(f"Root children count: {len(root['children'])}")
        def print_tree(node, level=0):
            if not isinstance(node, dict):
                return
            indent = "  " * level
            name = node.get("name", "Unknown")
            rank = node.get("rank", "Unknown")
            children = node.get("children", {})
            print(f"{indent}{name} ({rank})")
            for child in children.values():
                print_tree(child, level + 1)
        print("\nTree structure:")
        print_tree(root)
        return root

    @staticmethod
    def _convert_tree_for_display(tree: Dict) -> Dict:
        """Convert our tree structure to the format expected by TreeBuilder."""
        if not tree:
            print("Warning: Empty tree provided for conversion")
            return {}
        def convert_node(node: Dict) -> Dict:
            if not isinstance(node, dict):
                print(f"Warning: Invalid node type: {type(node)}")
                return {}
            new_node = {
                "id": node.get("id"),
                "name": node.get("name", ""),
                "rank": node.get("rank", ""),
                "common_name": node.get("common_name", ""),
                "children": {}
            }
            children = node.get("children", {})
            if isinstance(children, dict):
                sorted_children = sorted(
                    children.items(),
                    key=lambda x: (
                        {"stateofmatter": 0, "kingdom": 1, "phylum": 2, "class": 3,
                         "order": 4, "family": 5, "genus": 6, "species": 7}.get(x[1].get('rank', ''), 999),
                        x[1].get('name', '')
                    )
                )
                for child_id, child in sorted_children:
                    if isinstance(child, dict):
                        converted_child = convert_node(child)
                        if converted_child and converted_child.get("id"):
                            new_node["children"][str(child_id)] = converted_child
            return new_node
        return convert_node(tree)

    @staticmethod
    def debug_taxon_record(taxon_id: int):
        """Print debug information about a taxon's API and DB records."""
        print(f"\n=== Debug info for Taxon {taxon_id} ===")
        print("\nFetching from API...")
        api_record = INaturalistAPI.get_taxon_details(taxon_id)
        print("API Record:")
        print(f"  Name: {api_record.get('name', 'N/A')}")
        print(f"  Rank: {api_record.get('rank', 'N/A')}")
        print(f"  Common Name: {api_record.get('preferred_common_name', 'N/A')}")
        print(f"  Ancestor IDs: {api_record.get('ancestor_ids', [])}")
        print(f"  Full API record: {api_record}")
        print("\nFetching from Database...")
        db = Database.get_instance()
        db_record = db.get_cached_branch(taxon_id)
        if db_record:
            print("DB Record:")
            print(f"  Name: {db_record.get('name', 'N/A')}")
            print(f"  Rank: {db_record.get('rank', 'N/A')}")
            print(f"  Common Name: {db_record.get('common_name', 'N/A')}")
            print(f"  Ancestor IDs: {db_record.get('ancestor_ids', [])}")
            print(f"  Full DB record: {db_record}")
        else:
            print("DB Record: None")
        print("\nComparison:")
        if api_record and db_record:
            print("  Fields match?")
            print(f"    Name: {api_record.get('name') == db_record.get('name')}")
            print(f"    Rank: {api_record.get('rank') == db_record.get('rank')}")
            print(f"    Ancestor IDs: {api_record.get('ancestor_ids') == db_record.get('ancestor_ids')}")
        else:
            print("  Cannot compare - missing records")
        print("=" * 50)
