"""
ComputationGraphExecutor 单元测试。

使用内存中的 node_data_map，不依赖 Neo4j。
"""
import pytest

from domain.services.computation_graph_executor import ComputationGraphExecutor


class TestComputationGraphExecutor:
    """ComputationGraphExecutor 测试。"""

    def test_build_and_execute(self, sample_graph, sample_node_data_map):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        assert executor.graph is sample_graph
        assert executor.node_data_map is sample_node_data_map
        ok = executor.execute(verbose=False)
        assert ok is True
        # 100 * 5 = 500 -> subtotal; 500 * 0.1 = 50 -> tax
        data = executor.get_all_data_nodes()
        assert data["order_001"]["price"] == 100.0
        assert data["invoice_001"]["subtotal"] == 500.0
        assert data["invoice_001"]["tax"] == 50.0

    def test_get_node_data(self, sample_graph, sample_node_data_map):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        node_data = executor.get_node_data("invoice_001")
        assert node_data is not None
        assert node_data.get("subtotal") == 500.0
        assert node_data.get("tax") == 50.0
        assert executor.get_node_data("nonexistent") is None

    def test_update_node_property(self, sample_graph, sample_node_data_map):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.update_node_property("order_001", "price", 200.0)
        executor.execute(verbose=False)
        data = executor.get_all_data_nodes()
        assert data["order_001"]["price"] == 200.0
        assert data["invoice_001"]["subtotal"] == 1000.0  # 200 * 5
        assert data["invoice_001"]["tax"] == 100.0

    def test_snapshot_restore(self, sample_graph, sample_node_data_map):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        snapshot = executor.snapshot_data_nodes()
        assert "order_001" in snapshot
        assert "invoice_001" in snapshot
        assert snapshot["order_001"]["price"] == 100.0
        assert snapshot["invoice_001"]["subtotal"] == 500.0

        executor.update_node_property("order_001", "price", 999.0)
        executor.execute(verbose=False)
        assert executor.get_node_data("order_001")["price"] == 999.0

        executor.restore_data_nodes(snapshot)
        assert executor.get_node_data("order_001")["price"] == 100.0
        assert executor.get_node_data("invoice_001")["subtotal"] == 500.0

    def test_get_all_data_nodes_excludes_computation(self, sample_graph, sample_node_data_map):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        executor.execute(verbose=False)
        data = executor.get_all_data_nodes()
        assert "calc_subtotal" not in data
        assert "calc_tax" not in data
        assert "order_001" in data
        assert "invoice_001" in data
        for node_id, d in data.items():
            assert "is_computation" not in d or d.get("is_computation") is not True

    def test_execution_order_respects_dependencies(self, sample_graph, sample_node_data_map):
        executor = ComputationGraphExecutor(sample_graph, sample_node_data_map)
        order = executor._get_execution_order()
        assert order is not None
        idx_subtotal = order.index("calc_subtotal")
        idx_tax = order.index("calc_tax")
        assert idx_subtotal < idx_tax  # subtotal 必须在 tax 之前

    def test_single_node_graph(self, sample_graph, sample_node_data_map, output_specs, input_specs):
        """仅一个计算节点的图也能正确执行。"""
        from domain.models import ComputationGraph, ComputationNode, ComputationRelationship
        from domain.models import ComputationLevel, ComputationEngine, ComputationRelationType

        one_node = ComputationNode(
            id="only",
            name="only",
            level=ComputationLevel.PROPERTY,
            inputs=(input_specs["price"], input_specs["quantity"]),
            outputs=(output_specs["subtotal"],),
            code="price * quantity",
            engine=ComputationEngine.PYTHON,
        )
        rels = [
            ComputationRelationship(
                "r1", "order_001", "only", "p", ComputationRelationType.DEPENDS_ON, "property",
                datasource=input_specs["price"],
            ),
            ComputationRelationship(
                "r2", "order_001", "only", "q", ComputationRelationType.DEPENDS_ON, "property",
                datasource=input_specs["quantity"],
            ),
            ComputationRelationship(
                "r3", "only", "invoice_001", "o", ComputationRelationType.OUTPUT_TO, "property",
                data_output=output_specs["subtotal"],
            ),
        ]
        g = ComputationGraph(id="one")
        g = g.add_computation_node(one_node)
        for r in rels:
            g = g.add_computation_relationship(r)
        node_data = {"order_001": {"price": 10.0, "quantity": 3}, "invoice_001": {}}
        exec_one = ComputationGraphExecutor(g, node_data)
        ok = exec_one.execute(verbose=False)
        assert ok
        assert exec_one.get_node_data("invoice_001")["subtotal"] == 30.0
