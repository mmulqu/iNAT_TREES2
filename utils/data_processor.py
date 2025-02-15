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

                ancestors = taxon.get("ancestors", [])
                if not isinstance(ancestors, list):
                    ancestors = []

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
                    "taxon_kingdom": taxon.get("kingdom_name") or DataProcessor.get_ancestor_name(ancestors, "kingdom"),
                    "taxon_phylum": taxon.get("phylum_name") or DataProcessor.get_ancestor_name(ancestors, "phylum"),
                    "taxon_class": taxon.get("class_name") or DataProcessor.get_ancestor_name(ancestors, "class"),
                    "taxon_order": taxon.get("order_name") or DataProcessor.get_ancestor_name(ancestors, "order"),
                    "taxon_family": taxon.get("family_name") or DataProcessor.get_ancestor_name(ancestors, "family"),
                    "taxon_genus": taxon.get("genus_name") or DataProcessor.get_ancestor_name(ancestors, "genus")
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
        # Debug print to see what data we have
        print("\nDataFrame columns:", df.columns.tolist())
        print("\nSample row taxon names:")
        sample_row = df.iloc[0]
        for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
            print(f"{rank}: ID = {sample_row[rank]}, Name = {sample_row[f'taxon_{rank}']}")
            
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
                    # Handle species differently since it doesn't have a taxon_ prefix
                    if rank == "species":
                        taxon_name = row["name"]
                    else:
                        taxon_name = row[f"taxon_{rank}"]
                        
                    print(f"Creating node for {rank}: ID={taxon_id}, Name={taxon_name}")  # Debug print
                    
                    current_level[taxon_id] = {
                        "name": taxon_name,
                        "common_name": row["common_name"] if rank == "species" else "",
                        "rank": rank,
                        "children": {}
                    }
                current_level = current_level[taxon_id]["children"]
        
        print("\nFinal hierarchy structure:")
        def print_hierarchy(h, level=0):
            for tid, node in h.items():
                print("  " * level + f"{node['rank']}: {node['name']} (ID: {tid})")
                print_hierarchy(node['children'], level + 1)
        print_hierarchy(hierarchy)
        
        return hierarchy