import plotly.graph_objects as go
from typing import Dict, Tuple
import pandas as pd
import numpy as np

class TreeBuilder:
    @staticmethod
    def create_tree_structure(hierarchy: Dict) -> Tuple[Dict, Dict]:
        """Convert hierarchy to a format suitable for plotting."""
        nodes = {}
        edges = []
        name_mapping = {}
        node_counter = 0

        def traverse(node: Dict, parent_id: int = None) -> int:
            nonlocal node_counter
            current_id = node_counter
            node_counter += 1

            # Store node information
            nodes[current_id] = {
                "name": node.get("name", ""),
                "common_name": node.get("common_name", "")
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

        # Calculate node positions using a simple layered layout
        G = {i: [] for i in nodes.keys()}
        for parent, child in edges:
            G[parent].append(child)

        # Calculate positions with rank-based spacing
        pos = {}
        rank_spacing = {
            "kingdom": 200,
            "phylum": 150,
            "class": 120,
            "order": 100,
            "family": 80,
            "genus": 60,
            "species": 40
        }
        
        def calculate_positions(node_id, x=0, y=0, dx=1):
            pos[node_id] = (x, y)
            children = G[node_id]
            n_children = len(children)
            
            if n_children > 0:
                node_rank = nodes[node_id].get("rank", "species")
                spacing = rank_spacing.get(node_rank, 40)
                new_dx = dx * 0.7  # Reduced scaling factor for better spread
                total_width = (n_children - 1) * spacing
                start_y = y - total_width / 2
                
                for i, child in enumerate(children):
                    new_y = start_y + i * spacing
                    # Use evolutionary distance for x-position if available
                    new_x = x + (nodes[child].get("distance", 1) - nodes[node_id].get("distance", 0)) * 100
                    calculate_positions(child, new_x, new_y, new_dx)

        # Start layout calculation from root
        calculate_positions(0)

        # Create figure
        fig = go.Figure()

        # Add edges
        for parent, child in edges:
            fig.add_trace(go.Scatter(
                x=[pos[parent][0], pos[child][0]],
                y=[pos[parent][1], pos[child][1]],
                mode="lines",
                line=dict(color="#2E7D32", width=1),
                hoverinfo="skip",
                showlegend=False
            ))

        # Add nodes and labels
        for node_id, node_info in nodes.items():
            if node_info["name"]:  # Only add labels for named nodes
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