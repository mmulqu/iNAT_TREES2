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
                
                # Get actual family and genus from ancestors
                family_id = ancestor_ids_by_rank.get("family")
                genus_id = ancestor_ids_by_rank.get("genus")
                
                processed_data.append({
                    "observation_id": obs["id"],
                    "taxon_id": taxon["id"],
                    "name": taxon["name"],
                    "rank": taxon["rank"],
                    "kingdom": ancestor_ids_by_rank.get("kingdom"),
                    "phylum": ancestor_ids_by_rank.get("phylum"),
                    "class": ancestor_ids_by_rank.get("class"),
                    "order": ancestor_ids_by_rank.get("order"),
                    "family": family_id,
                    "genus": genus_id,
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
        print("\nSample row full data:")
        sample_row = df.iloc[0]
        print(sample_row)

        print("\nSample row taxon names:")
        for rank in ["kingdom", "phylum", "class", "order", "family", "genus", "species"]:
            if rank == "species":
                name = sample_row["name"]
            else:
                name = sample_row[f"taxon_{rank}"]
            print(f"{rank}: ID = {sample_row[rank]}, Name = {name}")
            
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