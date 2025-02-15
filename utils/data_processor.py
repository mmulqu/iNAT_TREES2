
import pandas as pd
from typing import List, Dict

class DataProcessor:
    @staticmethod
    def process_observations(observations: List[Dict]) -> pd.DataFrame:
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
                    "photo_url": obs.get("photos", [{}])[0].get("url", "")
                })
                
            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                print(f"ancestor_ids: {taxon.get('ancestor_ids')}")
                continue
                
        return pd.DataFrame(processed_data)

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
