import pandas as pd
from typing import List, Dict

class DataProcessor:
    @staticmethod
    def process_observations(observations: List[Dict]) -> pd.DataFrame:
        """Process raw observations into a structured DataFrame."""
        processed_data = []
        
        for obs in observations:
            if not obs.get("taxon"):
                continue
                
            taxon = obs["taxon"]
            processed_data.append({
                "observation_id": obs["id"],
                "taxon_id": taxon["id"],
                "name": taxon["name"],
                "rank": taxon["rank"],
                "kingdom": taxon.get("ancestor_ids", [None])[0],
                "phylum": taxon.get("ancestor_ids", [None, None])[1],
                "class": taxon.get("ancestor_ids", [None, None, None])[2],
                "order": taxon.get("ancestor_ids", [None, None, None, None])[3],
                "family": taxon.get("ancestor_ids", [None, None, None, None, None])[4],
                "genus": taxon.get("ancestor_ids", [None, None, None, None, None, None])[5],
                "species": taxon["id"],
                "common_name": taxon.get("preferred_common_name", ""),
                "observed_on": obs.get("observed_on"),
                "photo_url": obs.get("photos", [{}])[0].get("url", "")
            })
            
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
