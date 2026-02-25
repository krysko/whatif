from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InputSpec:
    """Specification for computation input"""
    source_type: str  # 'property', 'entity', 'graph'
    entity_type: str  # e.g., 'Product', 'Customer'
    property_name: str | None = None  # e.g., 'price', 'quantity'
    graph_name: str | None = None  # e.g., 'business_graph'
    node_id: str | None = None  # specific node reference


@dataclass(frozen=True, slots=True)
class OutputSpec:
    """Specification for computation output"""
    target_type: str  # 'property', 'entity', 'graph'
    entity_type: str  # e.g., 'Product', 'Customer'
    property_name: str | None = None  # e.g., 'total_price', 'status'
    graph_name: str | None = None  # e.g., 'result_graph'
