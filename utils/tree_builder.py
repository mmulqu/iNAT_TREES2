import plotly.graph_objects as go
from typing import Dict, List, Tuple, Set, Optional
import pandas as pd
import numpy as np

class TreeBuilder:
    @staticmethod
    def build_taxonomy_tree(taxa_data: List[Dict]) -> Dict:
        """
        Build a complete taxonomy tree from taxa data.

        Args:
            taxa_data: List of dictionaries containing taxon information
                      Each dict should have: taxon_id, name, rank, ancestor_ids
        """
        print("\nStarting tree building...")
        # Initialize the complete tree
        complete_tree = {}

        def add_taxon_to_tree(taxon: Dict, ancestors: List[int]):
            """Add a single taxon and its ancestors to the tree."""
            current_dict = complete_tree

            # First add all ancestors in order
            for ancestor_id in ancestors:
                # Find ancestor data
                ancestor_data = next(
                    (t for t in taxa_data if t['taxon_id'] == ancestor_id), 
                    None
                )
                if ancestor_data:
                    if ancestor_id not in current_dict:
                        current_dict[ancestor_id] = {
                            'id': ancestor_id,
                            'name': ancestor_data['name'],
                            'rank': ancestor_data['rank'],
                            'children': {},
                            'common_name': ancestor_data.get('common_name', '')
                        }
                    current_dict = current_dict[ancestor_id]['children']

            # Then add the taxon itself
            if taxon['taxon_id'] not in current_dict:
                current_dict[taxon['taxon_id']] = {
                    'id': taxon['taxon_id'],
                    'name': taxon['name'],
                    'rank': taxon['rank'],
                    'children': {},
                    'common_name': taxon.get('common_name', '')
                }

        # Process each taxon
        for taxon in taxa_data:
            try:
                # Parse ancestor_ids from string to list of integers if needed
                ancestor_ids = eval(taxon['ancestor_ids']) if isinstance(taxon['ancestor_ids'], str) else taxon['ancestor_ids']
                if ancestor_ids:
                    print(f"Processing {taxon['name']} with {len(ancestor_ids)} ancestors")
                    add_taxon_to_tree(taxon, ancestor_ids)
            except Exception as e:
                print(f"Error processing taxon {taxon.get('taxon_id', 'unknown')}: {e}")
                continue

        if not TreeBuilder.validate_tree(complete_tree):
            print("Warning: Built tree failed validation")

        return complete_tree

    @staticmethod
    def find_root_node(tree: Dict, root_id: int) -> Optional[Dict]:
        """Find and extract the subtree starting from a specific root ID."""
        def find_node(current_tree: Dict, target_id: int) -> Optional[Dict]:
            # Check if the current node is our target
            for node_id, node_data in current_tree.items():
                if int(node_id) == target_id:  # Convert string keys to int for comparison
                    return node_data

                # Recursively search children
                if 'children' in node_data:
                    result = find_node(node_data['children'], target_id)
                    if result:
                        return result
            return None

        return find_node(tree, root_id)

    @staticmethod
    def collect_all_taxa_ids(tree: Dict) -> Set[int]:
        """Collect all taxon IDs in the tree."""
        taxa_ids = set()

        def traverse(node: Dict):
            if 'id' in node:
                taxa_ids.add(node['id'])
            for child in node.get('children', {}).values():
                traverse(child)

        traverse(tree)
        return taxa_ids

    @staticmethod
    def validate_tree(tree: Dict) -> bool:
        """Validate that the tree is properly structured."""
        required_fields = {'id', 'name', 'rank', 'children'}

        def validate_node(node: Dict) -> bool:
            # Check that all required fields are present
            if not all(field in node for field in required_fields):
                print(f"Node missing required fields: {node.get('name', 'unknown')}")
                return False

            # Validate children recursively
            for child in node['children'].values():
                if not validate_node(child):
                    return False

            return True

        valid = all(validate_node(node) for node in tree.values())
        if not valid:
            print("Tree validation failed")
        return valid

    @staticmethod
    def create_tree_structure(hierarchy: Dict) -> Tuple[Dict, Dict]:
        """Convert hierarchy to a format suitable for plotting."""
        print("\nSTART OF HIERARCHY DEBUGGING")

        def print_node(node, level=0):
            indent = "  " * level
            name = node.get("name", "")
            rank = node.get("rank", "")
            print(f"{indent}Node - Name: {name}, Rank: {rank}")
            for child in node["children"].values():
                print_node(child, level + 1)

        print("Full hierarchy structure:")
        print_node({"children": hierarchy})

        nodes = {}
        edges = []
        node_counter = 0

        def traverse(node: Dict, parent_id: int = None) -> int:
            nonlocal node_counter
            current_id = node_counter
            node_counter += 1

            nodes[current_id] = {
                "name": node.get("name", ""),
                "common_name": node.get("common_name", ""),
                "rank": node.get("rank", ""),
            }

            if parent_id is not None:
                edges.append((parent_id, current_id))

            for child in node["children"].values():
                traverse(child, current_id)

            return current_id

        traverse({"children": hierarchy, "name": "", "common_name": ""})
        return nodes, edges

    @staticmethod
    def create_plotly_tree(hierarchy: Dict) -> go.Figure:
        """Create an interactive phylogenetic tree visualization using Plotly."""
        # Validate tree before visualization
        if not TreeBuilder.validate_tree({"root": hierarchy}):
            print("Warning: Tree validation failed before visualization")

        nodes, edges = TreeBuilder.create_tree_structure(hierarchy)

        # Build graph structure
        G = {i: [] for i in nodes.keys()}
        for parent, child in edges:
            G[parent].append(child)

        # Calculate positions
        pos = {}

        def get_leaf_count(node_id):
            children = G[node_id]
            if not children:
                return 1
            return sum(get_leaf_count(child) for child in children)

        def calculate_positions(node_id, x=0, y_start=0, vertical_spacing=1):
            children = G[node_id]

            if not children:
                pos[node_id] = (x, y_start)
                return y_start + vertical_spacing

            current_y = y_start
            child_x = x + 1

            child_y_positions = []
            for child in children:
                next_y = calculate_positions(child, child_x, current_y, vertical_spacing)
                child_y_positions.append(pos[child][1])
                current_y = next_y

            pos[node_id] = (x, sum(child_y_positions) / len(child_y_positions))
            return current_y

        leaf_count = get_leaf_count(0)
        vertical_spacing = 2 / (leaf_count + 1)
        calculate_positions(0, vertical_spacing=vertical_spacing)

        # Create figure
        fig = go.Figure()

        # Add edges
        for parent, child in edges:
            px, py = pos[parent]
            cx, cy = pos[child]

            path_x = [px, px, cx]
            path_y = [py, cy, cy]

            fig.add_trace(go.Scatter(
                x=path_x,
                y=path_y,
                mode="lines",
                line=dict(color="#2E7D32", width=1),
                hoverinfo="skip",
                showlegend=False
            ))

        # Add nodes for higher taxonomic ranks
        for node_id, node_info in nodes.items():
            if node_info.get("rank") != "species":
                name = node_info.get("name", "")
                rank = node_info.get("rank", "").title()

                hover_text = f"{rank}: {name}" if name else rank

                fig.add_trace(go.Scatter(
                    x=[pos[node_id][0]],
                    y=[pos[node_id][1]],
                    mode="markers",
                    marker=dict(size=6, color="#2E7D32"),
                    hoverinfo="text",
                    text=hover_text,
                    showlegend=False
                ))

        # Add species nodes and labels
        for node_id, node_info in nodes.items():
            if node_info.get("rank") == "species":
                label = f"{node_info['name']}"
                if node_info["common_name"]:
                    label += f"<br>{node_info['common_name']}"

                fig.add_trace(go.Scatter(
                    x=[pos[node_id][0]],
                    y=[pos[node_id][1]],
                    mode="markers+text",
                    text=[label],
                    textposition="middle right",
                    hoverinfo="text",
                    marker=dict(size=8, color="#2E7D32"),
                    showlegend=False
                ))

        # Update layout
        fig.update_layout(
            showlegend=False,
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=50, r=50, t=30, b=30),
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            hovermode="closest",
            height=800,
            width=1200
        )

        return fig