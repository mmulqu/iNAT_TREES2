import pandas as pd
from typing import List, Dict, Optional, Union, Any, Set, Tuple
from utils.taxonomy_cache import TaxonomyCache
from utils.database import Database
from utils.data_utils import normalize_ancestors

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

                # Process ancestors and build complete taxonomy
                for ancestor in ancestors:
                    rank = ancestor.get('rank', '')
                    if rank:
                        ancestor_names[rank] = ancestor.get('name', '')
                        ancestor_ids_by_rank[rank] = ancestor.get('id')

                # Fill in missing ranks from ancestor_ids if available
                if ancestor_ids:
                    db = Database.get_instance()

                    for aid in ancestor_ids:
                        if isinstance(aid, (int, str)):
                            try:
                                aid = int(aid)
                                # Skip if we already have this ID mapped
                                if aid not in ancestor_ids_by_rank.values():
                                    # Try to get cached data for this ancestor
                                    cached_data = db.get_cached_branch(aid)
                                    if cached_data:
                                        rank = cached_data.get('rank', '')
                                        if rank and rank not in ancestor_ids_by_rank:
                                            ancestor_names[rank] = cached_data.get('name', '')
                                            ancestor_ids_by_rank[rank] = aid
                            except ValueError:
                                print(f"Invalid ancestor ID: {aid}")

                # Ensure we have a complete taxonomy path
                # Most iNaturalist taxa have these standard taxonomic ranks
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

                # For species rank, use the taxon's own ID and name
                if taxon.get("rank") == "species":
                    processed_observation["species"] = taxon["id"]
                    processed_observation["taxon_species"] = taxon["name"]

                # If this is a direct child of the filter taxon, add the relationship
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
    def build_taxonomy_hierarchy(df: pd.DataFrame, taxonomic_group: Optional[str] = None) -> Dict:
        """Build filtered taxonomy hierarchy using the cached structure."""
        if df.empty:
            print("No data to build hierarchy from")
            return {}

        print("\nBuilding taxonomy hierarchy...")
        taxonomy_cache = TaxonomyCache()

        # Get unique species IDs from the observations
        species_ids = []
        for _, row in df.iterrows():
            rank = row.get("rank")
            if rank == "species" and pd.notna(row.get("taxon_id")):
                species_ids.append(int(row["taxon_id"]))
            elif pd.notna(row.get("species")):
                species_ids.append(int(row["species"]))

        species_ids = list(set(species_ids))  # Remove duplicates
        print(f"Found {len(species_ids)} unique species")

        # Get the appropriate root ID for the taxonomic group
        root_id = None
        if taxonomic_group and taxonomic_group in DataProcessor.TAXONOMIC_FILTERS:
            root_id = DataProcessor.TAXONOMIC_FILTERS[taxonomic_group]["id"]
            print(f"Found matching root for {taxonomic_group} with ID {root_id}")

        if root_id and species_ids:
            # Try to get filtered tree from cache
            print("Checking cache for filtered tree...")
            filtered_tree = taxonomy_cache.get_filtered_user_tree(root_id, species_ids)
            if filtered_tree:
                print("Using cached tree")
                return filtered_tree

        # If no cache, build directly from observations
        print("Building complete tree from observations...")
        complete_tree = DataProcessor._build_complete_tree(df, taxonomic_group)

        # Save the tree to cache if it was built successfully
        if complete_tree and root_id and species_ids:
            try:
                taxonomy_cache.save_tree(
                    root_id=root_id,
                    tree=complete_tree,
                    species_ids=species_ids
                )
                print(f"Saved tree to cache with root {root_id}")
            except Exception as e:
                print(f"Failed to save tree to cache: {e}")

        return complete_tree

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

        # Create Life node as the root
        tree = DataProcessor.create_node(
            taxon_id=48460,
            name="Life",
            rank="stateofmatter"
        )

        # Define the order of ranks
        ranks = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

        # First collect all unique taxa by rank and their relationships
        taxa_by_rank = {rank: {} for rank in ranks}
        parent_child_map = {}  # Track parent-child relationships

        for _, row in df.iterrows():
            prev_id = 48460  # Life is the root
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
                    # Record parent-child relationship
                    parent_child_map[taxon_id] = prev_id
                    prev_id = taxon_id

        # Build the tree maintaining proper parent-child relationships
        def add_to_tree(node_id: int, parent_node: Dict) -> None:
            """Recursively add nodes to the tree."""
            children = [tid for tid, pid in parent_child_map.items() if pid == node_id]

            for child_id in children:
                # Find the child's data
                child_data = None
                for rank_data in taxa_by_rank.values():
                    if child_id in rank_data:
                        child_data = rank_data[child_id]
                        break

                if child_data:
                    parent_node["children"][str(child_id)] = child_data
                    add_to_tree(child_id, child_data)

        # Start building from Life
        add_to_tree(48460, tree)

        return tree

    @staticmethod
    def _build_tree_from_dataframe(df: pd.DataFrame) -> Dict:
        """Build taxonomy tree directly from DataFrame."""
        print("\nBuilding tree from DataFrame...")
        print(f"Processing {len(df)} rows")

        # Debug print the DataFrame columns and a sample row
        print("\nDataFrame columns:", df.columns.tolist())
        print("\nSample row data:")
        if not df.empty:
            sample_row = df.iloc[0]
            for rank in ["stateofmatter"] + DataProcessor.TAXONOMIC_RANKS:
                print(f"{rank}: {sample_row.get(rank)}")
                print(f"taxon_{rank}: {sample_row.get(f'taxon_{rank}')}")

        # First pass: collect all unique taxa and their info
        taxa_info = {}

        # Add Life as the root
        root = {
            "id": 48460,
            "name": "Life",
            "rank": "stateofmatter",
            "common_name": "",
            "children": {}
        }

        # Process all other taxa
        for _, row in df.iterrows():
            # Add each taxon that exists in this row
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

            # Also add the observation taxon if it's not a standard rank
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

        # Second pass: build hierarchy starting from Life
        for _, row in df.iterrows():
            current_level = root["children"]

            # Build a full path for this observation
            path = []
            for rank in DataProcessor.TAXONOMIC_RANKS:
                if pd.notna(row.get(rank)):
                    path.append((rank, int(row[rank])))

            # If we have a path, add it to the tree
            if path:
                # Process each node in the path
                for i, (rank, taxon_id) in enumerate(path):
                    str_id = str(taxon_id)  # Convert to string for dictionary key

                    if str_id not in current_level and taxon_id in taxa_info:
                        print(f"Adding node to tree - ID: {taxon_id}, Rank: {rank}")
                        current_level[str_id] = taxa_info[taxon_id].copy()

                    # If this isn't the last node, move to its children
                    if i < len(path) - 1 and str_id in current_level:
                        current_level = current_level[str_id]["children"]

        print(f"\nFinal tree structure summary:")
        print(f"Root children count: {len(root['children'])}")

        # Debug print the tree structure
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
            """Convert a single node and its children."""
            if not isinstance(node, dict):
                print(f"Warning: Invalid node type: {type(node)}")
                return {}

            # Create the new node structure
            new_node = {
                "id": node.get("id"),
                "name": node.get("name", ""),
                "rank": node.get("rank", ""),
                "common_name": node.get("common_name", ""),
                "children": {}
            }

            # Sort and process children
            children = node.get("children", {})
            if isinstance(children, dict):
                # Sort children by rank and name
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

        # Convert the entire tree
        return convert_node(tree)