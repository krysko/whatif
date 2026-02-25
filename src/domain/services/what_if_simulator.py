"""
What-If Simulator

Handles what-if simulations for computation graphs.
Provides simulate_property_change (single change, optional Neo4j write-back) and
run_scenario (one or more property changes in isolation, returns baseline/scenario/diff).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from .computation_graph_executor import ComputationGraphExecutor
from .neo4j_graph_manager import Neo4jGraphManager


def _compute_diff(
    baseline: Dict[str, Dict[str, Any]],
    scenario: Dict[str, Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Compare baseline and scenario state; return list of changed (node_id, property_name, baseline_value, scenario_value).
    Only includes entries where the value differs. Covers all node_id and property_name present in either state.
    """
    diff: List[Dict[str, Any]] = []
    all_nodes = set(baseline.keys()) | set(scenario.keys())
    for node_id in all_nodes:
        b_props = baseline.get(node_id, {})
        s_props = scenario.get(node_id, {})
        all_props = set(b_props.keys()) | set(s_props.keys())
        for prop in all_props:
            b_val = b_props.get(prop)
            s_val = s_props.get(prop)
            if b_val != s_val:
                diff.append({
                    "node_id": node_id,
                    "property_name": prop,
                    "baseline_value": b_val,
                    "scenario_value": s_val,
                })
    return diff


@dataclass
class ScenarioRunResult:
    """Result of a single scenario run: baseline state, scenario state, and diff of changed properties."""

    baseline: Dict[str, Dict[str, Any]]  # node_id -> { prop -> value }
    scenario: Dict[str, Dict[str, Any]]
    diff: List[Dict[str, Any]]  # [{"node_id", "property_name", "baseline_value", "scenario_value"}, ...]


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

    async def run_scenario(
        self,
        property_changes: List[Tuple[str, str, Any]],
        title: str = "Scenario",
    ) -> ScenarioRunResult:
        """
        Run one scenario in isolation: apply the given property changes, re-execute, then restore executor state.
        Does not modify executor in-memory values; returns baseline, scenario state, and the diff between them.

        Args:
            property_changes: List of (node_id, property_name, new_value) to apply for this run.
            title: Optional title for optional console summary of the diff.

        Returns:
            ScenarioRunResult with baseline (state before scenario), scenario (state after execute),
            and diff (list of changed properties: node_id, property_name, baseline_value, scenario_value).
        """
        snapshot = self.executor.snapshot_data_nodes()
        baseline = self.executor.get_all_data_nodes()
        try:
            for node_id, property_name, new_value in property_changes:
                self.executor.update_node_property(node_id, property_name, new_value)
            self.executor.execute(verbose=False)
            scenario = self.executor.get_all_data_nodes()
            diff = _compute_diff(baseline, scenario)
            result = ScenarioRunResult(baseline=baseline, scenario=scenario, diff=diff)
            if title:
                print(f"\n[{title}] Diff (baseline -> scenario):")
                for d in diff:
                    print(f"  {d['node_id']}.{d['property_name']}: {d['baseline_value']} -> {d['scenario_value']}")
            return result
        finally:
            self.executor.restore_data_nodes(snapshot)
