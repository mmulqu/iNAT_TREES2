import pandas as pd
from typing import List, Dict, Optional, Set
from utils.taxonomy_cache import TaxonomyCache
from utils.tree_builder import TreeBuilder

class DataProcessor:
    TAXONOMIC_FILTERS = {
        "Insects": {"class": "Insecta", "id": 47158},
        "Fungi": {"kingdom": "Fungi", "id": 47170},
        "Plants": {"kingdom": "Plantae", "id": 47126},
        "Mammals": {"class": "Mammalia", "id": 40151},
        "Reptiles": {"class": "Reptilia", "id": 26036},
        "Amphibians": {"class": "Amphibia", "id": 20978}
    }

    TAXONOMIC_RANKS = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]

    @staticmethod
    def get_ancestor_name(ancestors: List[Dict], rank: str) -> str:
        """Extract ancestor name by rank from ancestors list."""
        for ancestor in ancestors:
            if ancestor.get("rank") == rank:
                return ancestor.get("name", "")
        return ""

    @staticmethod
    def process_observations(observations: List[Dict], taxonomic_group: Optional[str] = None) -> pd.DataFrame:
        """Process raw observations into a structured DataFrame."""
        if not observations:
            print("No observations to process")
            return pd.DataFrame()

        print("\nProcessing observations...")
        print(f"Total observations: {len(observations)}")

        if observations:
            print("\nFirst observation ancestors:")
            first_obs = observations[0]
            print("Taxon:", first_obs["taxon"]["name"])
            print("Ancestors:")
            for ancestor in first_obs["taxon"].get("ancestors", []):
                print(f"  {ancestor['rank']}: {ancestor['name']}")

        processed_data = []
        skipped_count = 0

        for obs in observations:
            try:
                if not obs.get("taxon") or not obs.get("id"):
                    skipped_count += 1
                    continue

                taxon = obs["taxon"]
                ancestors = taxon.get("ancestors", [])

                # Create mappings for both IDs and names
                ancestor_names = {}
                ancestor_ids_by_rank = {}
                for ancestor in ancestors:
                    if ancestor.get("rank") and ancestor.get("name"):
                        ancestor_names[ancestor["rank"]] = ancestor["name"]
                        ancestor_ids_by_rank[ancestor["rank"]] = ancestor["id"]

                # Ensure all taxonomic ranks are present in the data
                processed_observation = {
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon["name"],
                    "rank": taxon["rank"],
                    "common_name": taxon.get("preferred_common_name", ""),
                    "observed_on": obs.get("observed_on"),
                    "photo_url": obs.get("photos", [{}])[0].get("url", ""),
                }

                # Add rank-specific fields
                for rank in DataProcessor.TAXONOMIC_RANKS:
                    processed_observation[rank] = ancestor_ids_by_rank.get(rank)
                    processed_observation[f"taxon_{rank}"] = ancestor_names.get(rank, "")

                # For species rank, use the taxon's own ID and name
                if taxon["rank"] == "species":
                    processed_observation["species"] = taxon["id"]
                    processed_observation["taxon_species"] = taxon["name"]

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
        species_ids = df[df["rank"] == "species"]["taxon_id"].unique().tolist()
        print(f"Found {len(species_ids)} unique species")

        # Get the appropriate root ID for the taxonomic group first
        root_id = None
        if taxonomic_group and taxonomic_group in DataProcessor.TAXONOMIC_FILTERS:
            root_id = DataProcessor.TAXONOMIC_FILTERS[taxonomic_group]["id"]
            print(f"Using root ID {root_id} for {taxonomic_group}")

        if not root_id:
            # Try to find the most specific common ancestor
            for group, info in DataProcessor.TAXONOMIC_FILTERS.items():
                filter_id = info["id"]
                if any(filter_id == row["class"] for _, row in df.iterrows()):
                    root_id = filter_id
                    print(f"Found matching root for {group} with ID {root_id}")
                    break

        if root_id and species_ids:
            # Try to get filtered tree from cache
            print("Checking cache for filtered tree...")
            filtered_tree = taxonomy_cache.get_filtered_user_tree(root_id, species_ids)
            if filtered_tree:
                print("Using cached tree")
                return filtered_tree

        # If no cache or no root_id, build from DataFrame
        print("Building tree from DataFrame...")
        tree = DataProcessor._build_tree_from_dataframe(df)

        # Cache the newly built tree if we have a root_id
        if root_id and tree:
            print("Caching new tree...")
            taxonomy_cache.save_tree(
                root_id=root_id,
                tree=tree,
                species_ids=species_ids
            )

        return tree

    @staticmethod
    def _build_tree_from_dataframe(df: pd.DataFrame) -> Dict:
        """Build taxonomy tree directly from DataFrame."""
        hierarchy = {}
        print("\nBuilding tree from DataFrame...")
        print(f"Processing {len(df)} rows")

        # First pass: collect all unique taxa and their info
        taxa_info = {}
        for _, row in df.iterrows():
            for rank in DataProcessor.TAXONOMIC_RANKS:
                if pd.notna(row[rank]):
                    taxon_id = int(row[rank])
                    if taxon_id not in taxa_info:
                        if rank == "species":
                            name = row["name"]
                            common_name = row["common_name"]
                        else:
                            name = row[f"taxon_{rank}"]
                            common_name = ""

                        taxa_info[taxon_id] = {
                            "id": taxon_id,
                            "name": name,
                            "common_name": common_name,
                            "rank": rank,
                            "children": {}
                        }

        # Second pass: build hierarchy
        for _, row in df.iterrows():
            current_level = hierarchy
            current_path = []

            for rank in DataProcessor.TAXONOMIC_RANKS:
                if pd.isna(row[rank]):
                    break

                taxon_id = int(row[rank])
                current_path.append(taxon_id)

                if taxon_id not in current_level:
                    current_level[taxon_id] = taxa_info[taxon_id].copy()

                current_level = current_level[taxon_id]["children"]

        print(f"Built tree with {len(hierarchy)} top-level taxa")
        return hierarchy

    @staticmethod
    def validate_tree(tree: Dict) -> bool:
        """Validate the taxonomy tree structure."""
        required_fields = {'id', 'name', 'rank', 'children'}

        def validate_node(node: Dict) -> bool:
            if not all(field in node for field in required_fields):
                print(f"Node missing required fields: {node.get('name', 'unknown')}")
                return False

            return all(validate_node(child) for child in node['children'].values())

        return all(validate_node(node) for node in tree.values())