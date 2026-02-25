"""
What-If Simulator

Handles what-if simulations for computation graphs.
"""

from typing import Dict, List, Optional

from .computation_graph_executor import ComputationGraphExecutor
from .neo4j_graph_manager import Neo4jGraphManager


class WhatIfSimulator:
    """Handles what-if simulations for computation graphs"""

    def __init__(self, executor: ComputationGraphExecutor, neo4j_manager: Neo4jGraphManager):
        self.executor = executor
        self.neo4j_manager = neo4j_manager

    async def simulate_property_change(
        self,
        node_id: str,
        property_name: str,
        new_value,
        title: str = "Property Change",
    ) -> Dict:
        """
        Simulate a generic property change and return results. Original values are restored after the call.

        Args:
            node_id: Data node ID whose property is changed.
            property_name: Property name to change.
            new_value: New value for the property.
            output_node_id: If set (and output_targets is None), write this single node's outputs to Neo4j
                using the manager's default output properties.
            output_targets: If set, write multiple nodes to Neo4j: map of node_id -> list of output property names.
                Takes precedence over output_node_id when both are provided.
            title: Title for printed output.

        Returns:
            get_all_data_nodes() after the simulation (modified state), for callers to inspect or print summary.
        """
        snapshot = self.executor.snapshot_data_nodes()
        try:
            original_value = self.executor.get_node_data(node_id).get(property_name)
            self.executor.update_node_property(node_id, property_name, new_value)

            print(f"\n{'=' * 60}")
            print(f"What-If Simulation: {title}")
            print(f"{'=' * 60}")
            print(f"\nScenario: What if {node_id}.{property_name} changes from {original_value} to {new_value}?")
            print(f"\nRe-executing computations...")
            self.executor.execute(verbose=False)
            self.executor.print_node_data(f"Results After {title}")

            return self.executor.get_all_data_nodes()
        finally:
            self.executor.restore_data_nodes(snapshot)
