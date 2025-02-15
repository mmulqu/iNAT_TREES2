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
                    "taxon_phylum": taxon.get("phylum_name", ""),
                    "taxon_class": taxon.get("class_name", ""),
                    "taxon_order": taxon.get("order_name", ""),
                    "taxon_family": taxon.get("family_name", ""),
                    "taxon_genus": taxon.get("genus_name", "")
                })

            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                print(f"ancestor_ids: {taxon.get('ancestor_ids')}")
                continue

        df = pd.DataFrame(processed_data)

        # Filtering is now handled at the API level

        return df

    @staticmethod
    def build_taxonomy_hierarchy(df: pd.DataFrame, filter_rank: str = None, filter_taxon_id: int = None) -> Dict:
        """
        Build hierarchical taxonomy with optional filtering by rank/taxon.
        
        Args:
            df: DataFrame with taxonomic data
            filter_rank: Taxonomic rank to filter by (e.g., 'class', 'order')
            filter_taxon_id: ID of the taxon to filter by
        """
        hierarchy = {}
        
        for _, row in df.iterrows():
            current_level = hierarchy
            ancestor_chain = []
            
            for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
                if pd.isna(row[rank]):
                    break
                    
                taxon_id = row[rank]
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