"""
领域模型单元测试：ComputationGraph、ComputationNode、ComputationRelationship、InputSpec、OutputSpec。
"""
import pytest

from domain.models import (
    ComputationLevel,
    ComputationEngine,
    ComputationRelationType,
    InputSpec,
    OutputSpec,
    ComputationNode,
    ComputationRelationship,
    ComputationGraph,
)


class TestInputSpec:
    """InputSpec 测试。"""

    def test_create(self):
        spec = InputSpec("property", "Order", "price")
        assert spec.source_type == "property"
        assert spec.entity_type == "Order"
        assert spec.property_name == "price"
        assert spec.graph_name is None
        assert spec.node_id is None

    def test_optional_fields(self):
        spec = InputSpec("graph", "Product", graph_name="business_graph", node_id="n1")
        assert spec.graph_name == "business_graph"
        assert spec.node_id == "n1"


class TestOutputSpec:
    """OutputSpec 测试。"""

    def test_create(self):
        spec = OutputSpec("property", "Invoice", "subtotal")
        assert spec.target_type == "property"
        assert spec.entity_type == "Invoice"
        assert spec.property_name == "subtotal"


class TestComputationNode:
    """ComputationNode 测试。"""

    def test_create(self, sample_computation_nodes):
        node = sample_computation_nodes["calc_subtotal"]
        assert node.id == "calc_subtotal"
        assert node.name == "calculate_subtotal"
        assert node.level == ComputationLevel.PROPERTY
        assert node.code == "price * quantity"
        assert node.engine == ComputationEngine.PYTHON
        assert len(node.inputs) == 2
        assert len(node.outputs) == 1

    def test_get_property_default(self, sample_computation_nodes):
        node = sample_computation_nodes["calc_subtotal"]
        assert node.get_property("missing") is None
        assert node.get_property("missing", 42) == 42

    def test_with_properties(self, sample_computation_nodes):
        node = sample_computation_nodes["calc_subtotal"]
        new_node = node.with_properties(priority=1)
        assert new_node.properties.get("priority") == 1
        assert node.properties != new_node.properties
        assert new_node.id == node.id


class TestComputationRelationship:
    """ComputationRelationship 测试。"""

    def test_depends_on_relationship(self, input_specs):
        rel = ComputationRelationship(
            "r1", "order_001", "calc_subtotal",
            "price_dep", ComputationRelationType.DEPENDS_ON, "property",
            datasource=input_specs["price"],
        )
        assert rel.source_id == "order_001"
        assert rel.target_id == "calc_subtotal"
        assert rel.relation_type == ComputationRelationType.DEPENDS_ON
        assert rel.datasource is not None
        assert rel.datasource.property_name == "price"

    def test_output_to_relationship(self, output_specs):
        rel = ComputationRelationship(
            "r2", "calc_subtotal", "invoice_001",
            "subtotal_out", ComputationRelationType.OUTPUT_TO, "property",
            data_output=output_specs["subtotal"],
        )
        assert rel.relation_type == ComputationRelationType.OUTPUT_TO
        assert rel.data_output.property_name == "subtotal"

    def test_with_properties(self, input_specs):
        rel = ComputationRelationship(
            "r1", "a", "b", "n", ComputationRelationType.DEPENDS_ON, "property",
            datasource=input_specs["price"],
        )
        new_rel = rel.with_properties(weight=1)
        assert new_rel.get_property("weight") == 1


class TestComputationGraph:
    """ComputationGraph 测试。"""

    def test_empty_graph(self):
        g = ComputationGraph(id="g1")
        assert g.id == "g1"
        assert len(g.computation_nodes) == 0
        assert len(g.computation_relationships) == 0
        assert g.get_data_node_ids() == set()

    def test_get_computation_node(self, sample_graph):
        node = sample_graph.get_computation_node("calc_subtotal")
        assert node is not None
        assert node.name == "calculate_subtotal"
        assert sample_graph.get_computation_node("nonexistent") is None

    def test_get_outgoing_incoming(self, sample_graph):
        out = sample_graph.get_outgoing_relationships("order_001")
        assert len(out) == 2  # price, quantity
        inc = sample_graph.get_incoming_relationships("calc_subtotal")
        assert len(inc) == 2

    def test_get_dependencies(self, sample_graph):
        deps = sample_graph.get_dependencies("calc_subtotal")
        assert len(deps) == 0  # 依赖的是数据节点 order_001，不是计算节点
        deps_tax = sample_graph.get_dependencies("calc_tax")
        assert len(deps_tax) == 0  # 依赖的是 invoice_001（数据节点）

    def test_get_dependents(self, sample_graph):
        # calc_subtotal 的 output_to 目标是 invoice_001（数据节点），不是计算节点
        dependents = sample_graph.get_dependents("calc_subtotal")
        assert len(dependents) == 0
        dependents_order = sample_graph.get_dependents("order_001")
        assert len(dependents_order) == 0  # get_dependents 只返回 computation nodes

    def test_get_data_node_ids(self, sample_graph):
        data_ids = sample_graph.get_data_node_ids()
        assert "order_001" in data_ids
        assert "invoice_001" in data_ids
        assert "calc_subtotal" not in data_ids
        assert "calc_tax" not in data_ids

    def test_get_output_properties_by_data_node(self, sample_graph):
        out = sample_graph.get_output_properties_by_data_node()
        assert "invoice_001" in out
        assert "subtotal" in out["invoice_001"]
        assert "tax" in out["invoice_001"]
        assert "order_001" not in out

    def test_add_computation_node_immutable(self, sample_graph, sample_computation_nodes):
        new_node = ComputationNode(
            id="calc_extra",
            name="extra",
            level=ComputationLevel.PROPERTY,
            inputs=(),
            outputs=(),
            code="1",
            engine=ComputationEngine.PYTHON,
        )
        new_graph = sample_graph.add_computation_node(new_node)
        assert sample_graph.get_computation_node("calc_extra") is None
        assert new_graph.get_computation_node("calc_extra") is not None
        assert len(new_graph.computation_nodes) == len(sample_graph.computation_nodes) + 1

    def test_add_computation_relationship_immutable(self, sample_graph, input_specs):
        rel = ComputationRelationship(
            "rel_new", "order_001", "calc_subtotal",
            "new_dep", ComputationRelationType.DEPENDS_ON, "property",
            datasource=InputSpec("property", "Order", "extra"),
        )
        new_graph = sample_graph.add_computation_relationship(rel)
        assert sample_graph.get_computation_relationship("rel_new") is None
        assert new_graph.get_computation_relationship("rel_new") is not None
