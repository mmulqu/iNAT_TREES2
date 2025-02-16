import pandas as pd
from typing import List, Dict, Optional
from utils.taxonomy_cache import TaxonomyCache

class DataProcessor:
    TAXONOMIC_FILTERS = {
        "Insects": {"class": "Insecta", "id": 47158},
        "Fungi": {"kingdom": "Fungi", "id": 47170},
        "Plants": {"kingdom": "Plantae", "id": 47126},
        "Mammals": {"class": "Mammalia", "id": 40151},
        "Reptiles": {"class": "Reptilia", "id": 26036},
        "Amphibians": {"class": "Amphibia", "id": 20978}
    }

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
        if observations:
            print("\nFirst observation ancestors:")
            first_obs = observations[0]
            print("Taxon:", first_obs["taxon"]["name"])
            print("Ancestors:")
            for ancestor in first_obs["taxon"].get("ancestors", []):
                print(f"  {ancestor['rank']}: {ancestor['name']}")

        processed_data = []

        for obs in observations:
            try:
                if not obs.get("taxon") or not obs.get("id"):
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

                processed_data.append({
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon["name"],
                    "rank": taxon["rank"],
                    "kingdom": ancestor_ids_by_rank.get("kingdom"),
                    "phylum": ancestor_ids_by_rank.get("phylum"),
                    "class": ancestor_ids_by_rank.get("class"),
                    "order": ancestor_ids_by_rank.get("order"),
                    "family": ancestor_ids_by_rank.get("family"),
                    "genus": ancestor_ids_by_rank.get("genus"),
                    "species": taxon["id"],
                    "common_name": taxon.get("preferred_common_name", ""),
                    "observed_on": obs.get("observed_on"),
                    "photo_url": obs.get("photos", [{}])[0].get("url", ""),
                    "taxon_kingdom": ancestor_names.get("kingdom", ""),
                    "taxon_phylum": ancestor_names.get("phylum", ""),
                    "taxon_class": ancestor_names.get("class", ""),
                    "taxon_order": ancestor_names.get("order", ""),
                    "taxon_family": ancestor_names.get("family", ""),
                    "taxon_genus": ancestor_names.get("genus", "")
                })

            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                continue

        return pd.DataFrame(processed_data)

    @staticmethod
    def build_taxonomy_hierarchy(df: pd.DataFrame, filter_rank: str = None, filter_taxon_id: int = None) -> Dict:
        """Build filtered taxonomy hierarchy using the cached structure."""
        taxonomy_cache = TaxonomyCache()

        # Get unique species IDs from the observations
        species_ids = df["species"].unique().tolist()

        # Determine the appropriate root ID based on filter or default to kingdom
        root_id = None
        if filter_rank and filter_taxon_id:
            root_id = filter_taxon_id
        else:
            # Try to find the most specific common ancestor
            for group, info in DataProcessor.TAXONOMIC_FILTERS.items():
                if df["taxon_" + info["class"].lower()].iloc[0] == info["class"]:
                    root_id = info["id"]
                    break

        if root_id:
            # Get filtered tree for the user's species
            filtered_tree = taxonomy_cache.get_filtered_user_tree(root_id, species_ids)
            if filtered_tree:
                return filtered_tree

        # Fallback to building tree from DataFrame if cache miss
        return DataProcessor._build_tree_from_dataframe(df)

    @staticmethod
    def _build_tree_from_dataframe(df: pd.DataFrame) -> Dict:
        """Fallback method to build tree directly from DataFrame."""
        hierarchy = {}

        for _, row in df.iterrows():
            current_level = hierarchy

            for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
                if pd.isna(row[rank]):
                    break

                taxon_id = int(row[rank])

                if taxon_id not in current_level:
                    if rank == "species":
                        name = row["name"]
                        common_name = row["common_name"]
                    else:
                        name = row[f"taxon_{rank}"]
                        common_name = ""

                    current_level[taxon_id] = {
                        "name": name,
                        "common_name": common_name,
                        "rank": rank,
                        "children": {}
                    }
                current_level = current_level[taxon_id]["children"]

        return hierarchy