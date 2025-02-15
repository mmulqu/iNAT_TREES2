
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
        """Process observations with complete taxonomic information."""
        processed_data = []
        
        for obs in observations:
            try:
                if not obs.get("taxon") or not obs.get("id"):
                    continue
                    
                taxon = obs["taxon"]
                ancestors = taxon.get("ancestors", [])
                
                # Initialize all possible ranks with None
                taxon_data = {
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon["name"],
                    "rank": taxon["rank"],
                    "rank_level": taxon.get("rank_level"),
                    "iconic_taxon_id": taxon.get("iconic_taxon_id"),
                    "iconic_taxon_name": taxon.get("iconic_taxon_name"),
                    # Initialize all taxonomic ranks
                    "kingdom": None,
                    "phylum": None,
                    "class": None,
                    "order": None,
                    "family": None,
                    "genus": None,
                    "species": None,
                    # Initialize names and levels
                    "kingdom_name": None,
                    "phylum_name": None,
                    "class_name": None,
                    "order_name": None,
                    "family_name": None,
                    "genus_name": None,
                    "species_name": None,
                    "kingdom_level": None,
                    "phylum_level": None,
                    "class_level": None,
                    "order_level": None,
                    "family_level": None,
                    "genus_level": None,
                    "species_level": None,
                }
                
                # Fill in ancestor data
                for ancestor in ancestors:
                    rank = ancestor["rank"]
                    if rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
                        taxon_data[rank] = ancestor["id"]
                        taxon_data[f"{rank}_name"] = ancestor["name"]
                        taxon_data[f"{rank}_level"] = ancestor.get("rank_level")
                
                processed_data.append(taxon_data)
                
            except Exception as e:
                print(f"Error processing observation {obs.get('id')}: {str(e)}")
                continue
            
        df = pd.DataFrame(processed_data)
        
        # Apply taxonomic filter if specified
        if taxonomic_group and taxonomic_group in DataProcessor.TAXONOMIC_FILTERS:
            filter_criteria = DataProcessor.TAXONOMIC_FILTERS[taxonomic_group]
            for rank, value in filter_criteria.items():
                mask = df[f"{rank}_name"].fillna('').str.lower() == value.lower()
                if mask.any():  # Only apply filter if matches found
                    df = df[mask]
                else:
                    return pd.DataFrame()  # Return empty if no matches
        
        return df

    @staticmethod
    def build_taxonomy_hierarchy(df: pd.DataFrame, filter_rank: str = None, filter_taxon_id: int = None) -> Dict:
        """Build hierarchical taxonomy with evolutionary distances based on rank levels."""
        def get_distance(rank_level):
            """Convert iNat rank levels to distances"""
            return (100 - rank_level) / 20.0 if rank_level else 1.0
        
        sorted_df = df.sort_values(by=["kingdom", "phylum", "class", "order", "family", "genus", "species"])
        hierarchy = {}
        last_common_ancestor = {}
        
        for _, row in sorted_df.iterrows():
            current_level = hierarchy
            current_distance = 0
            ancestor_chain = []
            
            for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
                if pd.isna(row[rank]):
                    continue
                    
                taxon_id = row[rank]
                rank_level = row.get(f"{rank}_level")
                current_distance += get_distance(rank_level)
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
                        "name": row[f"{rank}_name"] if rank != "species" else row["name"],
                        "common_name": row.get("common_name", ""),
                        "rank": rank,
                        "distance": current_distance,
                        "children": {}
                    }
                    last_common_ancestor[rank] = taxon_id
                    
                current_level = current_level[taxon_id]["children"]
        
        return hierarchy
