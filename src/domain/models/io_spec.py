"""
输入/输出规格：描述计算节点从哪读、往哪写。

- InputSpec：source_type（如 property）、entity_type、property_name 等，与 DEPENDS_ON 的 datasource 对应。
- OutputSpec：target_type、entity_type、property_name，与 OUTPUT_TO 的 data_output 对应。
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InputSpec:
    """计算输入规格：来源类型、实体类型、属性名等。"""
    source_type: str  # 'property', 'entity', 'graph'
    entity_type: str  # e.g., 'Product', 'Customer'
    property_name: str | None = None  # e.g., 'price', 'quantity'
    graph_name: str | None = None  # e.g., 'business_graph'
    node_id: str | None = None  # specific node reference


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """计算输出规格：目标类型、实体类型、属性名等。"""
    target_type: str  # 'property', 'entity', 'graph'
    entity_type: str  # e.g., 'Product', 'Customer'
    property_name: str | None = None  # e.g., 'total_price', 'status'
    graph_name: str | None = None  # e.g., 'result_graph'
