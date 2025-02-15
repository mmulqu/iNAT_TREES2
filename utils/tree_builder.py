
import plotly.graph_objects as go
from typing import Dict, Tuple
import pandas as pd
import numpy as np

class TreeBuilder:
    @staticmethod
    def create_tree_structure(hierarchy: Dict) -> Tuple[Dict, Dict]:
        """Convert hierarchy to a format suitable for plotting."""
        print("\nSTART OF HIERARCHY DEBUGGING")
        
        # Debug print for hierarchy
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
            
            # Debug print for each node as we process it
            print(f"\nProcessing node {current_id}:")
            print(f"Name: {node.get('name')}")
            print(f"Rank: {node.get('rank')}")

            nodes[current_id] = {
                "name": node.get("name", ""),
                "common_name": node.get("common_name", ""),
                "rank": node.get("rank", ""),
            }

            # Add edge from parent if exists
            if parent_id is not None:
                edges.append((parent_id, current_id))

            # Process children
            for child in node["children"].values():
                traverse(child, current_id)

            return current_id

        # Start traversal from root
        traverse({"children": hierarchy, "name": "", "common_name": ""})

        return nodes, edges

    @staticmethod
    def create_plotly_tree(hierarchy: Dict) -> go.Figure:
        """Create an interactive phylogenetic tree visualization using Plotly."""
        nodes, edges = TreeBuilder.create_tree_structure(hierarchy)

        # Build graph structure for traversal
        G = {i: [] for i in nodes.keys()}
        for parent, child in edges:
            G[parent].append(child)

        # Calculate positions with improved bottom-up approach
        pos = {}
        
        def get_leaf_count(node_id):
            """Get count of leaf nodes under this node"""
            children = G[node_id]
            if not children:
                return 1
            return sum(get_leaf_count(child) for child in children)
            
        def calculate_positions(node_id, x=0, y_start=0, vertical_spacing=1):
            """Calculate x,y positions bottom-up"""
            children = G[node_id]
            
            if not children:
                # Leaf node
                pos[node_id] = (x, y_start)
                return y_start + vertical_spacing
                
            # Calculate children positions
            current_y = y_start
            child_x = x + 1  # Horizontal spacing
            
            # Position each child and collect their y-coordinates
            child_y_positions = []
            for child in children:
                next_y = calculate_positions(child, child_x, current_y, vertical_spacing)
                child_y_positions.append(pos[child][1])
                current_y = next_y
            
            # Position this node at average of children's y-coordinates
            pos[node_id] = (x, sum(child_y_positions) / len(child_y_positions))
            
            return current_y

        # Start positioning from root with adjusted spacing
        leaf_count = get_leaf_count(0)
        vertical_spacing = 2 / (leaf_count + 1)  # Adjust spacing based on number of leaves
        calculate_positions(0, vertical_spacing=vertical_spacing)

        # Create figure
        fig = go.Figure()

        # Add right-angled edges
        for parent, child in edges:
            px, py = pos[parent]
            cx, cy = pos[child]
            
            # Create right-angled path
            path_x = [px, px, cx]
            path_y = [py, cy, cy]
            
            fig.add_trace(go.Scatter(
                x=path_x,
                y=path_y,
                mode="lines",
                line=dict(
                    color="#2E7D32",
                    width=1
                ),
                hoverinfo="skip",
                showlegend=False
            ))

        # Add nodes and hover text for higher taxonomic ranks (non-species)
        for node_id, node_info in nodes.items():
            if node_info.get("rank") != "species":
                name = node_info.get("name", "")
                rank = node_info.get("rank", "").title()
                
                # Format as "Rank: Name"
                hover_text = f"{rank}: {name}" if name else rank
                
                fig.add_trace(go.Scatter(
                    x=[pos[node_id][0]],
                    y=[pos[node_id][1]],
                    mode="markers",
                    marker=dict(
                        size=6,
                        color="#2E7D32"
                    ),
                    hoverinfo="text",
                    text=hover_text,
                    showlegend=False
                ))

        # Add nodes and labels for species
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
