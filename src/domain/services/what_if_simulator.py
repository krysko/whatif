"""
What-If Simulator

Handles what-if simulations for computation graphs.
Provides run_scenario(property_changes, title): run one or more property changes in isolation,
returns ScenarioRunResult with baseline, scenario, diff and extended fields; does not modify executor memory.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

from .computation_graph_executor import ComputationGraphExecutor
from .neo4j_graph_manager import Neo4jGraphManager


@dataclass
class NodeError:
    """Structured error for a single computation node during scenario execution."""

    node_id: str
    message: str
    exception: Optional[Exception] = None


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


def _property_changes_to_overrides(
    property_changes: List[Tuple[str, str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Convert list of (node_id, property_name, new_value) to Dict[node_id, Dict[prop, value]]."""
    overrides: Dict[str, Dict[str, Any]] = {}
    for node_id, property_name, new_value in property_changes:
        if node_id not in overrides:
            overrides[node_id] = {}
        overrides[node_id][property_name] = new_value
    return overrides


def _build_outputs_per_node(
    graph: Any,
    scenario: Dict[str, Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build node_id -> { output_prop -> value } from graph output specs and scenario state."""
    if not hasattr(graph, "get_output_properties_by_data_node"):
        return {}
    output_props_by_node = graph.get_output_properties_by_data_node()
    out: Dict[str, Dict[str, Any]] = {}
    for node_id, prop_names in output_props_by_node.items():
        node_state = scenario.get(node_id, {})
        out[node_id] = {p: node_state.get(p) for p in prop_names if p in node_state}
    return out


@dataclass
class ScenarioRunResult:
    """Result of a single scenario run: baseline state, scenario state, diff, and structured metadata."""

    baseline: Dict[str, Dict[str, Any]]  # node_id -> { prop -> value }
    scenario: Dict[str, Dict[str, Any]]
    diff: List[Dict[str, Any]]  # [{"node_id", "property_name", "baseline_value", "scenario_value"}, ...]
    # Extended fields for API/UI and multi-scenario comparison
    overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # node_id -> { prop -> value } applied in this run
    outputs_per_node: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # node_id -> { output_prop -> value } (key outputs only)
    affected_node_ids: List[str] = field(default_factory=list)  # data node ids that changed (appear in diff)
    errors: List[NodeError] = field(default_factory=list)  # computation errors during execute
    success: bool = True  # False if any computation node failed


def format_scenario_result(
    result: ScenarioRunResult,
    label: str = "Scenario",
    *,
    max_diff_items: int = 20,
    log_fn: Optional[Any] = None,
) -> None:
    """
    Format and log a ScenarioRunResult for demo/console: overrides, affected nodes,
    outputs per node, diff, and success/errors.
    """
    out = log_fn or logger.info
    out("  --- %s ---", label)
    if result.overrides:
        out("  输入覆盖 (overrides):")
        for node_id, props in result.overrides.items():
            out("    %s: %s", node_id, props)
    if result.affected_node_ids:
        out("  受影响节点: %s", ", ".join(result.affected_node_ids))
    if result.outputs_per_node:
        out("  关键输出 (outputs_per_node):")
        for node_id, props in result.outputs_per_node.items():
            out("    %s: %s", node_id, props)
    out("  属性变化 (diff, 共 %s 项):", len(result.diff))
    for d in result.diff[:max_diff_items]:
        out("    %s.%s: %s -> %s",
            d["node_id"], d["property_name"],
            d["baseline_value"], d["scenario_value"])
    if len(result.diff) > max_diff_items:
        out("    ... 其余 %s 项", len(result.diff) - max_diff_items)
    if not result.success and result.errors:
        out("  执行失败 (success=False), 错误:")
        for e in result.errors:
            out("    [%s] %s", e.node_id, e.message)
    else:
        out("  执行状态: success=%s", result.success)
    out("")


class WhatIfSimulator:
    """Handles what-if simulations for computation graphs"""

    def __init__(self, executor: ComputationGraphExecutor, neo4j_manager: Neo4jGraphManager):
        self.executor = executor
        self.neo4j_manager = neo4j_manager

    async def run_scenario(
        self,
        property_changes: List[Tuple[str, str, Any]],
        title: str = "Scenario",
        *,
        verbose: bool = False,
    ) -> ScenarioRunResult:
        """
        Run one scenario in isolation: apply the given property changes, re-execute, then restore executor state.
        Does not modify executor in-memory values; returns baseline, scenario state, and the diff between them.

        Args:
            property_changes: List of (node_id, property_name, new_value) to apply for this run.
            title: Optional title for optional console summary of the diff.
            verbose: If True, log the computation process (each node execution and result) during scenario run.

        Returns:
            ScenarioRunResult with baseline (state before scenario), scenario (state after execute),
            and diff (list of changed properties: node_id, property_name, baseline_value, scenario_value).
        """
        snapshot = self.executor.snapshot_data_nodes()
        baseline = self.executor.get_all_data_nodes()
        try:
            for node_id, property_name, new_value in property_changes:
                self.executor.update_node_property(node_id, property_name, new_value)
            if verbose:
                logger.info("[What-If] 计算过程:")
            self.executor.execute(verbose=verbose)
            scenario = self.executor.get_all_data_nodes()
            diff = _compute_diff(baseline, scenario)
            overrides = _property_changes_to_overrides(property_changes)
            affected_node_ids = sorted({d["node_id"] for d in diff})
            outputs_per_node = _build_outputs_per_node(self.executor.graph, scenario)
            result = ScenarioRunResult(
                baseline=baseline,
                scenario=scenario,
                diff=diff,
                overrides=overrides,
                outputs_per_node=outputs_per_node,
                affected_node_ids=affected_node_ids,
                errors=[],  # executor does not yet return errors
                success=True,
            )
            if title:
                logger.info("[%s] Diff (baseline -> scenario):", title)
                for d in diff:
                    logger.info(
                        "  %s.%s: %s -> %s",
                        d['node_id'], d['property_name'],
                        d['baseline_value'], d['scenario_value']
                    )
            return result
        finally:
            self.executor.restore_data_nodes(snapshot)
