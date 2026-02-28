"""
计算图执行器：基于 NetworkX 的拓扑执行与单节点求值。

流程：将 ComputationGraph + node_data_map 转为有向图 -> 依赖图拓扑排序 -> 按序执行每个计算节点。
单节点执行：从 DEPENDS_ON 来源收集变量 -> eval(code) -> 按 OUTPUT_TO 写回后继节点。
支持 snapshot/restore 与 update_node_property，供 What-If 场景在内存中改值后重跑并恢复。
"""

import copy
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import networkx as nx

logger = logging.getLogger(__name__)

from ..models import (
    ComputationRelationType,
    ComputationGraph,
)


class ComputationGraphExecutor:
    """基于 NetworkX 的计算图执行器：建图、拓扑序执行、单节点 eval、快照/恢复。"""

    def __init__(self, graph: ComputationGraph, node_data_map: Dict[str, Dict]):
        self.graph = graph
        self.node_data_map = node_data_map
        self.G = self._build_networkx_graph()

    def _build_networkx_graph(self) -> nx.DiGraph:
        """将计算图与数据节点转为 NetworkX 有向图：数据节点带 is_computation=False，计算节点带 code/engine/priority。"""
        G = nx.DiGraph()

        # Add data nodes
        for node_id, node_data in self.node_data_map.items():
            G.add_node(node_id, **node_data, is_computation=False, priority=0)

        # Add computation nodes
        for node_id, node in self.graph.computation_nodes.items():
            G.add_node(
                node_id,
                name=node.name,
                code=node.code,
                engine=node.engine.value,
                is_computation=True,
                priority=node.priority,
            )

        # Add edges
        for G, rel in [(G, rel) for rel in self.graph.computation_relationships.values()]:
            prop = None
            if rel.relation_type == ComputationRelationType.DEPENDS_ON:
                prop = rel.datasource.property_name if hasattr(rel, "datasource") and rel.datasource else None
                G.add_edge(rel.source_id, rel.target_id, relation_type="DEPENDS_ON", property_name=prop)
            elif rel.relation_type == ComputationRelationType.OUTPUT_TO:
                prop = rel.data_output.property_name if hasattr(rel, "data_output") and rel.data_output else None
                G.add_edge(rel.source_id, rel.target_id, relation_type="OUTPUT_TO", property_name=prop)

        return G

    def _get_dependency_graph(self) -> nx.DiGraph:
        """Extract dependency graph for topological sorting.

        Includes:
        1. DEPENDS_ON edges (data -> computation): B reads from A, so A before B.
        2. Writer-before-reader edges (computation -> computation): when comp A writes
           to (data_node, prop) and comp B reads from (data_node, prop), add A -> B
           so that calc_production_ready_days runs after calc_actual_start_days, etc.
        Uses self.graph.computation_relationships so multiple (data_node, comp) with
        different properties are all considered (G has one edge per (s,t) so would lose one).
        """
        dep_graph = nx.DiGraph()
        dep_graph.add_nodes_from(self.G.nodes())
        dep_graph.add_edges_from([
            (source, target) for source, target, data in self.G.edges(data=True)
            if data.get("relation_type") == "DEPENDS_ON"
        ])
        # Writer -> reader from relationship list (preserves multiple props per data_node->comp)
        outputs = []  # (writer_comp, data_node, property_name)
        reads = []    # (data_node, reader_comp, property_name)
        for rel in self.graph.computation_relationships.values():
            if rel.relation_type == ComputationRelationType.OUTPUT_TO and getattr(rel, "data_output", None):
                outputs.append((rel.source_id, rel.target_id, rel.data_output.property_name))
            elif rel.relation_type == ComputationRelationType.DEPENDS_ON and getattr(rel, "datasource", None):
                reads.append((rel.source_id, rel.target_id, rel.datasource.property_name))
        for (writer, data_node, prop) in outputs:
            for (dn, reader, read_prop) in reads:
                if data_node == dn and prop == read_prop and writer != reader:
                    dep_graph.add_edge(writer, reader)
        return dep_graph

    def _get_execution_order(self) -> Optional[List[str]]:
        """按依赖图拓扑序得到执行顺序；同层按 priority 升序、再按 node id 稳定排序。若存在环则返回 None。"""
        dep_graph = self._get_dependency_graph()
        try:
            key = lambda n: (self.G.nodes[n].get("priority", 0), n)
            return list(nx.lexicographical_topological_sort(dep_graph, key=key))
        except nx.NetworkXError as e:
            logger.error("Graph contains a cycle: %s", e)
            return None

    def _execute_node(self, node_id: str, verbose: bool = True) -> Optional[float]:
        """执行单个计算节点：从 DEPENDS_ON 来源收集变量 -> eval(code) -> 按 OUTPUT_TO 写回后继。"""
        node_data = self.G.nodes[node_id]

        if not node_data.get("is_computation"):
            return None

        if verbose:
            logger.info("Executing: %s (%s)", node_id, node_data.get('name'))
            logger.info("  Code: %s", node_data.get('code'))

        # Gather input variables from incoming DEPENDS_ON edges only (by source + property_name).
        # If the source node does not have the property, pass None so the computation can define
        # behavior for missing data (e.g. default to False/0) without mutating raw data.
        variables = {}
        for rel in self.graph.computation_relationships.values():
            if rel.relation_type != ComputationRelationType.DEPENDS_ON or rel.target_id != node_id:
                continue
            if not getattr(rel, "datasource", None) or not rel.datasource.property_name:
                continue
            src_id = rel.source_id
            prop = rel.datasource.property_name
            if src_id in self.G.nodes:
                variables[prop] = self.G.nodes[src_id].get(prop, None)

        # Execute computation (inject datetime/timedelta for date expressions)
        code = node_data.get("code", "")
        safe_globals = {"datetime": datetime, "timedelta": timedelta}
        try:
            result = eval(code, safe_globals, variables)
            if verbose:
                logger.info("  Result: %s", result)

            # Update successors via OUTPUT_TO edges
            for successor in self.G.successors(node_id):
                edge_data = self.G.edges[node_id, successor]
                if edge_data.get("relation_type") == "OUTPUT_TO":
                    property_name = edge_data.get("property_name")
                    if property_name:
                        self.G.nodes[successor][property_name] = result
                        if verbose:
                            logger.info("  -> Updated %s.%s = %s", successor, property_name, result)
            return result
        except Exception as e:
            if verbose:
                logger.error("  Error: %s", e)
            return None

    def execute(self, verbose: bool = True) -> bool:
        """按拓扑序执行全部计算节点；返回是否成功（有环时 False）。"""
        order = self._get_execution_order()
        if order is None:
            return False

        if verbose:
            logger.info("Execution order: %s", " -> ".join(order))

        for node_id in order:
            self._execute_node(node_id, verbose)
            if verbose and self.G.nodes[node_id].get("is_computation"):
                logger.info("")

        return True

    def update_node_property(self, node_id: str, property_name: str, value):
        """Update a property value on a data node"""
        if node_id in self.G.nodes:
            self.G.nodes[node_id][property_name] = value

    def snapshot_data_nodes(self) -> Dict[str, Dict]:
        """深拷贝当前所有数据节点状态，供 What-If 结束后 restore_data_nodes(snapshot) 恢复。"""
        return {
            node_id: copy.deepcopy(dict(data))
            for node_id, data in self.G.nodes(data=True)
            if not data.get("is_computation")
        }

    def restore_data_nodes(self, snapshot: Dict[str, Dict]) -> None:
        """Restore data nodes from a snapshot returned by snapshot_data_nodes()."""
        for node_id, data in snapshot.items():
            if node_id in self.G.nodes:
                self.G.nodes[node_id].clear()
                self.G.nodes[node_id].update(data)

    def get_node_data(self, node_id: str) -> Optional[Dict]:
        """Get current data for a node"""
        if node_id in self.G.nodes:
            return dict(self.G.nodes[node_id])
        return None

    def get_all_data_nodes(self) -> Dict[str, Dict]:
        """Get all data nodes"""
        return {
            node_id: {k: v for k, v in data.items() if k != "is_computation"}
            for node_id, data in self.G.nodes(data=True)
            if not data.get("is_computation")
        }

    def print_node_data(self, title: str = "Current Node Data"):
        """Log current data for all nodes"""
        logger.info("%s", title)
        logger.info("=" * 50)

        for node_id, data in self.G.nodes(data=True):
            if not data.get("is_computation"):
                logger.info("[%s]", node_id)
                for key, value in data.items():
                    if key != "is_computation":
                        logger.info("  %s: %s", key, value)
