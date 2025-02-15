import pandas as pd
from typing import List, Dict

class DataProcessor:
    @staticmethod
    def process_observations(observations: List[Dict]) -> pd.DataFrame:
        """Process raw observations into a structured DataFrame."""
        processed_data = []
        
        for obs in observations:
            # Skip invalid observations
            if not obs.get("taxon") or not obs.get("id"):
                continue
                
            taxon = obs["taxon"]
            
            # Skip if taxon is at root level (Life) or missing crucial data
            if taxon.get("rank") == "life" or not taxon.get("ancestor_ids"):
                continue
                
            # Skip if ancestor_ids is empty or invalid
            ancestor_ids = taxon.get("ancestor_ids", [])
            if not ancestor_ids or len(ancestor_ids) < 2:  # Need at least kingdom level
                continue
                
            processed_data.append({
                "observation_id": obs["id"],
                "taxon_id": taxon["id"],
                "name": taxon["name"],
                "rank": taxon["rank"],
                "kingdom": next(iter(taxon.get("ancestor_ids", [])), None),
                "phylum": next(iter(taxon.get("ancestor_ids", [])[1:]), None),
                "class": next(iter(taxon.get("ancestor_ids", [])[2:]), None),
                "order": next(iter(taxon.get("ancestor_ids", [])[3:]), None),
                "family": next(iter(taxon.get("ancestor_ids", [])[4:]), None),
                "genus": next(iter(taxon.get("ancestor_ids", [])[5:]), None),
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
