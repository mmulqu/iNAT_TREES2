import pandas as pd
from typing import List, Dict, Optional

class DataProcessor:
    @staticmethod
    def get_ancestor_name(ancestors: List[Dict], rank: str) -> str:
        """Extract ancestor name by rank from ancestors list."""
        for ancestor in ancestors:
            if ancestor.get("rank") == rank:
                return ancestor.get("name", "")
        return ""

    @staticmethod
    def get_ancestor_id(ancestors: List[Dict], rank: str) -> Optional[int]:
        """Extract ancestor id by rank from ancestors list."""
        for ancestor in ancestors:
            if ancestor.get("rank") == rank:
                return ancestor.get("id")
        return None

    TAXONOMIC_FILTERS = {
        "Insects": {"class": "Insecta"},
        "Fungi": {"kingdom": "Fungi"},
        "Plants": {"kingdom": "Plantae"},
        "Mammals": {"class": "Mammalia"},
        "Reptiles": {"class": "Reptilia"},
        "Amphibians": {"class": "Amphibia"}
    }

    @staticmethod
    def process_observations(observations: List[Dict], taxonomic_group: Optional[str] = None) -> pd.DataFrame:
        """Process raw observations into a structured DataFrame."""
        processed_data = []

        for obs in observations:
            try:
                if not obs.get("taxon") or not obs.get("id"):
                    continue

                taxon = obs["taxon"]
                ancestors = taxon.get("ancestors", [])
                if not isinstance(ancestors, list):
                    ancestors = []

                # Extract both id and name for each rank
                ranks = ["kingdom", "phylum", "class", "order", "family", "genus"]
                rank_data = {}
                for rank in ranks:
                    rank_data[rank] = DataProcessor.get_ancestor_id(ancestors, rank)
                    rank_data[f"taxon_{rank}"] = taxon.get(f"{rank}_name") or DataProcessor.get_ancestor_name(ancestors, rank)

                processed_data.append({
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon["name"],
                    "rank": taxon["rank"],
                    **rank_data,
                    "species": taxon["id"],
                    "common_name": taxon.get("preferred_common_name", ""),
                    "observed_on": obs.get("observed_on"),
                    "photo_url": obs.get("photos", [{}])[0].get("url", "")
                })

            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                continue

        df = pd.DataFrame(processed_data)
        return df

    @staticmethod
    def build_taxonomy_hierarchy(df: pd.DataFrame, filter_rank: str = None, filter_taxon_id: int = None) -> Dict:
        """Build hierarchical taxonomy with optional filtering by rank/taxon."""
        hierarchy = {}

        for _, row in df.iterrows():
            current_level = hierarchy
            ancestor_chain = []

            for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
                taxon_id = row[rank]
                if pd.isna(taxon_id):
                    break

                ancestor_chain.append((rank, taxon_id))

                matches_filter = (
                    (filter_rank is None and filter_taxon_id is None) or
                    (filter_rank == rank and filter_taxon_id == taxon_id) or
                    any(ancestor[1] == filter_taxon_id for ancestor in ancestor_chain)
                )

                if not matches_filter:
                    continue

                if taxon_id not in current_level:
                    current_level[taxon_id] = {
                        "name": row[f"taxon_{rank}"] if rank != "species" else row["name"],
                        "common_name": row["common_name"] if rank == "species" else "",
                        "rank": rank,
                        "children": {}
                    }
                current_level = current_level[taxon_id]["children"]

        return hierarchy