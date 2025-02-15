import pandas as pd
from typing import List, Dict, Optional

class DataProcessor:
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
                ancestor_ids = taxon.get("ancestor_ids", [])

                # More defensive check of ancestor_ids
                if not isinstance(ancestor_ids, list):
                    continue

                # Create a padded version of ancestor_ids
                padded_ancestors = ancestor_ids + [None] * 7  # Ensure we have enough elements

                processed_data.append({
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon["name"],
                    "rank": taxon["rank"],
                    "kingdom": padded_ancestors[0],
                    "phylum": padded_ancestors[1],
                    "class": padded_ancestors[2],
                    "order": padded_ancestors[3],
                    "family": padded_ancestors[4],
                    "genus": padded_ancestors[5],
                    "species": taxon["id"],
                    "common_name": taxon.get("preferred_common_name", ""),
                    "observed_on": obs.get("observed_on"),
                    "photo_url": obs.get("photos", [{}])[0].get("url", ""),
                    "taxon_kingdom": taxon.get("kingdom_name", ""),
                    "taxon_class": taxon.get("class_name", "")
                })

            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                print(f"ancestor_ids: {taxon.get('ancestor_ids')}")
                continue

        df = pd.DataFrame(processed_data)

        # Apply taxonomic filter if specified
        if taxonomic_group and taxonomic_group in DataProcessor.TAXONOMIC_FILTERS:
            filter_criteria = DataProcessor.TAXONOMIC_FILTERS[taxonomic_group]
            for field, value in filter_criteria.items():
                if field == "kingdom":
                    df = df[df["taxon_kingdom"] == value]
                elif field == "class":
                    df = df[df["taxon_class"] == value]

        return df

    @staticmethod
    def build_taxonomy_hierarchy(df: pd.DataFrame) -> Dict:
        """Build a hierarchical taxonomy structure from the DataFrame."""
        hierarchy = {}

        for _, row in df.iterrows():
            current_level = hierarchy
            for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
                if pd.isna(row[rank]):
                    break

                taxon_id = row[rank]
                if taxon_id not in current_level:
                    current_level[taxon_id] = {
                        "name": row["name"] if rank == "species" else "",
                        "common_name": row["common_name"] if rank == "species" else "",
                        "children": {}
                    }
                current_level = current_level[taxon_id]["children"]

        return hierarchy