"""
Pytest 配置与公共 fixture。

运行测试前将 src 加入 Python 路径。
"""
import sys
from pathlib import Path

import pytest

# 将项目 src 加入路径，便于 import domain
src_path = Path(__file__).resolve().parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

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


@pytest.fixture
def input_specs():
    """常用 InputSpec 构造 fixture。"""
    return {
        "price": InputSpec("property", "Order", "price"),
        "quantity": InputSpec("property", "Order", "quantity"),
        "tax_rate": InputSpec("property", "Invoice", "tax_rate"),
        "subtotal": InputSpec("property", "Invoice", "subtotal"),
    }


@pytest.fixture
def output_specs():
    """常用 OutputSpec 构造 fixture。"""
    return {
        "subtotal": OutputSpec("property", "Invoice", "subtotal"),
        "tax": OutputSpec("property", "Invoice", "tax"),
    }


@pytest.fixture
def sample_computation_nodes(input_specs, output_specs):
    """两个计算节点：calc_subtotal, calc_tax。"""
    calc_subtotal = ComputationNode(
        id="calc_subtotal",
        name="calculate_subtotal",
        level=ComputationLevel.PROPERTY,
        inputs=(input_specs["price"], input_specs["quantity"]),
        outputs=(output_specs["subtotal"],),
        code="price * quantity",
        engine=ComputationEngine.PYTHON,
    )
    calc_tax = ComputationNode(
        id="calc_tax",
        name="calculate_tax",
        level=ComputationLevel.PROPERTY,
        inputs=(input_specs["subtotal"], input_specs["tax_rate"]),
        outputs=(output_specs["tax"],),
        code="subtotal * tax_rate",
        engine=ComputationEngine.PYTHON,
    )
    return {"calc_subtotal": calc_subtotal, "calc_tax": calc_tax}


@pytest.fixture
def sample_graph(sample_computation_nodes, input_specs, output_specs):
    """
    简单计算图：Order -> calc_subtotal -> Invoice; Invoice -> calc_tax -> Invoice.
    数据节点: order_001, invoice_001.
    """
    calc_subtotal = sample_computation_nodes["calc_subtotal"]
    calc_tax = sample_computation_nodes["calc_tax"]
    relationships = [
        ComputationRelationship(
            "rel_price", "order_001", "calc_subtotal",
            "price_depends", ComputationRelationType.DEPENDS_ON, "property",
            datasource=input_specs["price"],
        ),
        ComputationRelationship(
            "rel_quantity", "order_001", "calc_subtotal",
            "quantity_depends", ComputationRelationType.DEPENDS_ON, "property",
            datasource=input_specs["quantity"],
        ),
        ComputationRelationship(
            "rel_subtotal_out", "calc_subtotal", "invoice_001",
            "subtotal_result", ComputationRelationType.OUTPUT_TO, "property",
            data_output=output_specs["subtotal"],
        ),
        ComputationRelationship(
            "rel_subtotal_in", "invoice_001", "calc_tax",
            "subtotal_depends", ComputationRelationType.DEPENDS_ON, "property",
            datasource=input_specs["subtotal"],
        ),
        ComputationRelationship(
            "rel_tax_rate", "invoice_001", "calc_tax",
            "tax_rate_depends", ComputationRelationType.DEPENDS_ON, "property",
            datasource=input_specs["tax_rate"],
        ),
        ComputationRelationship(
            "rel_tax_out", "calc_tax", "invoice_001",
            "tax_result", ComputationRelationType.OUTPUT_TO, "property",
            data_output=output_specs["tax"],
        ),
    ]
    graph = ComputationGraph(id="test_graph")
    graph = graph.add_computation_node(calc_subtotal)
    graph = graph.add_computation_node(calc_tax)
    for rel in relationships:
        graph = graph.add_computation_relationship(rel)
    return graph


@pytest.fixture
def sample_node_data_map():
    """与 sample_graph 对应的初始数据节点数据。"""
    return {
        "order_001": {
            "order_id": "ORD-001",
            "price": 100.0,
            "quantity": 5,
        },
        "invoice_001": {
            "invoice_id": "INV-001",
            "tax_rate": 0.1,
        },
    }
