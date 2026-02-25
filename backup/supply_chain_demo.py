"""
Supply Chain Computation Graph Demo

Demonstrates a multi-node computation graph for supply chain pricing calculations.
Shows how ComputationNode can connect to properties of multiple data nodes using
DEPENDS_ON and OUTPUT_TO relationships across the supply chain.

Graph Structure:
- Raw Material (multiple types)
- Parts (assembled from materials)
- Final Product (assembled from parts with packaging and shipping costs)
"""

import asyncio
import sys
from pathlib import Path
import networkx as nx

# Add src to Python path
src_path = Path(__file__).parent.parent / "src"
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
from domain.services import Neo4jDataProvider, ComputationExecutor

# ============================================================================
# Constants and Configuration
# ============================================================================

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"

# Data node IDs
RAW_MATERIAL_A_ID = "raw_material_a"
RAW_MATERIAL_B_ID = "raw_material_b"
PART_X_ID = "part_x"
PART_Y_ID = "part_y"
PRODUCT_ID = "final_product"

# Output property names
OUTPUT_PROPERTIES = [
    "total_cost", "markup_price", "packaged_price",
    "shipping_cost", "final_retail_price", "profit_margin"
]

# ============================================================================
# Graph Construction
# ============================================================================

def build_supply_chain_graph() -> tuple[ComputationGraph, dict]:
    """Build a multi-node supply chain computation graph

    Returns:
        (graph, node_data_map) - graph definition and initial node data
    """

    # ==================== Input Specifications ====================

    # Raw Material A inputs
    rm_a_base_cost = InputSpec("property", "RawMaterial", "base_cost")
    rm_a_quantity = InputSpec("property", "RawMaterial", "quantity")
    rm_a_transport_cost = InputSpec("property", "RawMaterial", "transport_cost")

    # Raw Material B inputs
    rm_b_base_cost = InputSpec("property", "RawMaterial", "base_cost")
    rm_b_quantity = InputSpec("property", "RawMaterial", "quantity")
    rm_b_transport_cost = InputSpec("property", "RawMaterial", "transport_cost")

    # Part X inputs (uses Raw Material A)
    part_x_assembly_cost = InputSpec("property", "Part", "assembly_cost")
    part_x_material_a_cost = InputSpec("property", "Part", "material_a_cost")
    part_x_overhead = InputSpec("property", "Part", "overhead_rate")

    # Part Y inputs (uses Raw Material B)
    part_y_assembly_cost = InputSpec("property", "Part", "assembly_cost")
    part_y_material_b_cost = InputSpec("property", "Part", "material_b_cost")
    part_y_overhead = InputSpec("property", "Part", "overhead_rate")

    # Final Product inputs
    prod_assembly_cost = InputSpec("property", "Product", "assembly_cost")
    prod_part_x_cost = InputSpec("property", "Product", "part_x_cost")
    prod_part_y_cost = InputSpec("property", "Product", "part_y_cost")
    prod_markup_rate = InputSpec("property", "Product", "markup_rate")
    prod_packaging_cost = InputSpec("property", "Product", "packaging_cost")
    prod_shipping_weight = InputSpec("property", "Product", "shipping_weight")
    prod_shipping_rate = InputSpec("property", "Product", "shipping_rate")
    prod_tax_rate = InputSpec("property", "Product", "tax_rate")

    # Computed value inputs for downstream calculations
    rm_a_total_cost = InputSpec("property", "RawMaterial", "total_cost")
    rm_b_total_cost = InputSpec("property", "RawMaterial", "total_cost")
    part_x_total_cost = InputSpec("property", "Part", "total_cost")
    part_y_total_cost = InputSpec("property", "Part", "total_cost")
    prod_total_cost = InputSpec("property", "Product", "total_cost")
    prod_markup_price = InputSpec("property", "Product", "markup_price")
    prod_packaged_price = InputSpec("property", "Product", "packaged_price")
    prod_shipping_cost = InputSpec("property", "Product", "shipping_cost")
    prod_final_price = InputSpec("property", "Product", "final_retail_price")

    # ==================== Output Specifications ====================

    # Raw Material outputs
    rm_a_total_output = OutputSpec("property", "RawMaterial", "total_cost")
    rm_b_total_output = OutputSpec("property", "RawMaterial", "total_cost")

    # Part outputs
    part_x_total_output = OutputSpec("property", "Part", "total_cost")
    part_y_total_output = OutputSpec("property", "Part", "total_cost")

    # Product outputs
    prod_total_output = OutputSpec("property", "Product", "total_cost")
    prod_markup_output = OutputSpec("property", "Product", "markup_price")
    prod_packaged_output = OutputSpec("property", "Product", "packaged_price")
    prod_shipping_output = OutputSpec("property", "Product", "shipping_cost")
    prod_final_output = OutputSpec("property", "Product", "final_retail_price")
    prod_profit_output = OutputSpec("property", "Product", "profit_margin")

    # ==================== Computation Nodes ====================

    # --- Raw Material Computations ---

    # calc_rm_a_total: total_cost = (base_cost + transport_cost) * quantity
    calc_rm_a_total = ComputationNode(
        id="calc_rm_a_total",
        name="calculate_raw_material_a_total",
        level=ComputationLevel.PROPERTY,
        inputs=(rm_a_base_cost, rm_a_transport_cost, rm_a_quantity),
        outputs=(rm_a_total_output,),
        code="(base_cost + transport_cost) * quantity",
        engine=ComputationEngine.PYTHON,
    )

    # calc_rm_b_total: total_cost = (base_cost + transport_cost) * quantity
    calc_rm_b_total = ComputationNode(
        id="calc_rm_b_total",
        name="calculate_raw_material_b_total",
        level=ComputationLevel.PROPERTY,
        inputs=(rm_b_base_cost, rm_b_transport_cost, rm_b_quantity),
        outputs=(rm_b_total_output,),
        code="(base_cost + transport_cost) * quantity",
        engine=ComputationEngine.PYTHON,
    )

    # --- Part Computations ---

    # calc_part_x_total: total_cost = (material_a_cost + assembly_cost) * (1 + overhead_rate)
    calc_part_x_total = ComputationNode(
        id="calc_part_x_total",
        name="calculate_part_x_total",
        level=ComputationLevel.PROPERTY,
        inputs=(part_x_material_a_cost, part_x_assembly_cost, part_x_overhead),
        outputs=(part_x_total_output,),
        code="(material_a_cost + assembly_cost) * (1 + overhead_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # calc_part_y_total: total_cost = (material_b_cost + assembly_cost) * (1 + overhead_rate)
    calc_part_y_total = ComputationNode(
        id="calc_part_yy_total",
        name="calculate_part_y_total",
        level=ComputationLevel.PROPERTY,
        inputs=(part_y_material_b_cost, part_y_assembly_cost, part_y_overhead),
        outputs=(part_y_total_output,),
        code="(material_b_cost + assembly_cost) * (1 + overhead_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # --- Product Computations ---

    # calc_prod_total: total_cost = part_x_cost + part_y_cost + assembly_cost
    calc_prod_total = ComputationNode(
        id="calc_prod_total",
        name="calculate_product_total",
        level=ComputationLevel.PROPERTY,
        inputs=(prod_part_x_cost, prod_part_y_cost, prod_assembly_cost),
        outputs=(prod_total_output,),
        code="part_x_cost + part_y_cost + assembly_cost",
        engine=ComputationEngine.PYTHON,
    )

    # calc_prod_markup: markup_price = total_cost * (1 + markup_rate)
    calc_prod_markup = ComputationNode(
        id="calc_prod_markup",
        name="calculate_markup_price",
        level=ComputationLevel.PROPERTY,
        inputs=(prod_total_cost, prod_markup_rate),
        outputs=(prod_markup_output,),
        code="total_cost * (1 + markup_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # calc_prod_packaged: packaged_price = markup_price + packaging_cost
    calc_prod_packaged = ComputationNode(
        id="calc_prod_packaged",
        name="calculate_packaged_price",
        level=ComputationLevel.PROPERTY,
        inputs=(prod_markup_price, prod_packaging_cost),
        outputs=(prod_packaged_output,),
        code="markup_price + packaging_cost",
        engine=ComputationEngine.PYTHON,
    )

    # calc_prod_shipping: shipping_cost = shipping_weight * shipping_rate
    calc_prod_shipping = ComputationNode(
        id="calc_prod_shipping",
        name="calculate_shipping_cost",
        level=ComputationLevel.PROPERTY,
        inputs=(prod_shipping_weight, prod_shipping_rate),
        outputs=(prod_shipping_output,),
        code="shipping_weight * shipping_rate",
        engine=ComputationEngine.PYTHON,
    )

    # calc_prod_final: final_retail_price = (packaged_price + shipping_cost) * (1 + tax)
    calc_prod_final = ComputationNode(
        id="calc_prod_final",
        name="calculate_final_retail_price",
        level=ComputationLevel.PROPERTY,
        inputs=(prod_packaged_price, prod_shipping_cost, prod_tax_rate),
        outputs=(prod_final_output,),
        code="(packaged_price + shipping_cost) * (1 + tax_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # calc_prod_profit: profit_margin = final_retail_price - total_cost
    calc_prod_profit = ComputationNode(
        id="calc_prod_profit",
        name="calculate_profit_margin",
        level=ComputationLevel.PROPERTY,
        inputs=(prod_final_price, prod_total_cost),
        outputs=(prod_profit_output,),
        code="final_retail_price - total_cost",
        engine=ComputationEngine.PYTHON,
    )

    # ==================== Build Computation Graph ====================

    graph = ComputationGraph(id="supply_chain_computation_graph")

    # Add all computation nodes
    computation_nodes = [
        calc_rm_a_total, calc_rm_b_total,
        calc_part_x_total, calc_part_y_total,
        calc_prod_total, calc_prod_markup, calc_prod_packaged,
        calc_prod_shipping, calc_prod_final, calc_prod_profit,
    ]
    for node in computation_nodes:
        graph = graph.add_computation_node(node)

    # ==================== Build Relationships ====================

    relationships = []

    # --- Raw Material A Dependencies ---
    relationships.extend([
        ComputationRelationship("rel_rm_a_base", RAW_MATERIAL_A_ID, "calc_rm_a_total",
            "base_cost_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=rm_a_base_cost),
        ComputationRelationship("rel_rm_a_transport", RAW_MATERIAL_A_ID, "calc_rm_a_total",
            "transport_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=rm_a_transport_cost),
        ComputationRelationship("rel_rm_a_qty", RAW_MATERIAL_A_ID, "calc_rm_a_total",
            "quantity_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=rm_a_quantity),
        ComputationRelationship("rel_rm_a_output", "calc_rm_a_total", RAW_MATERIAL_A_ID,
            "total_cost_result", ComputationRelationType.OUTPUT_TO, "property", data_output=rm_a_total_output),
    ])

    # --- Raw Material B Dependencies ---
    relationships.extend([
        ComputationRelationship("rel_rm_b_base", RAW_MATERIAL_B_ID, "calc_rm_b_total",
            "base_cost_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=rm_b_base_cost),
        ComputationRelationship("rel_rm_b_transport", RAW_MATERIAL_B_ID, "calc_rm_b_total",
            "transport_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=rm_b_transport_cost),
        ComputationRelationship("rel_rm_b_qty", RAW_MATERIAL_B_ID, "calc_rm_b_total",
            "quantity_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=rm_b_quantity),
        ComputationRelationship("rel_rm_b_output", "calc_rm_b_total", RAW_MATERIAL_B_ID,
            "total_cost_result", ComputationRelationType.OUTPUT_TO, "property", data_output=rm_b_total_output),
    ])

    # --- Part X Dependencies (uses Raw Material A) ---
    relationships.extend([
        ComputationRelationship("rel_part_x_mat_a", PART_X_ID, "calc_part_x_total",
            "material_a_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=part_x_material_a_cost),
        ComputationRelationship("rel_part_x_assembly", PART_X_ID, "calc_part_x_total",
            "assembly_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=part_x_assembly_cost),
        ComputationRelationship("rel_part_x_overhead", PART_X_ID, "calc_part_x_total",
            "overhead_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=part_x_overhead),
        ComputationRelationship("rel_part_x_output", "calc_part_x_total", PART_X_ID,
            "total_cost_result", ComputationRelationType.OUTPUT_TO, "property", data_output=part_x_total_output),
    ])

    # --- Part Y Dependencies (uses Raw Material B) ---
    relationships.extend([
        ComputationRelationship("rel_part_y_mat_b", PART_Y_ID, "calc_part_yy_total",
            "material_b_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=part_y_material_b_cost),
        ComputationRelationship("rel_part_y_assembly", PART_Y_ID, "calc_part_yy_total",
            "assembly_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=part_y_assembly_cost),
        ComputationRelationship("rel_part_y_overhead", PART_Y_ID, "calc_part_yy_total",
            "overhead_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=part_y_overhead),
        ComputationRelationship("rel_part_y_output", "calc_part_yy_total", PART_Y_ID,
            "total_cost_result", ComputationRelationType.OUTPUT_TO, "property", data_output=part_y_total_output),
    ])

    # --- Final Product Dependencies ---
    relationships.extend([
        ComputationRelationship("rel_prod_part_x", PRODUCT_ID, "calc_prod_total",
            "part_x_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_part_x_cost),
        ComputationRelationship("rel_prod_part_y", PRODUCT_ID, "calc_prod_total",
            "part_y_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_part_y_cost),
        ComputationRelationship("rel_prod_assembly", PRODUCT_ID, "calc_prod_total",
            "assembly_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_assembly_cost),
        ComputationRelationship("rel_prod_total_output", "calc_prod_total", PRODUCT_ID,
            "total_cost_result", ComputationRelationType.OUTPUT_TO, "property", data_output=prod_total_output),
    ])

    # --- Markup Calculation ---
    relationships.extend([
        ComputationRelationship("rel_prod_total_to_markup", PRODUCT_ID, "calc_prod_markup",
            "total_cost_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_total_cost),
        ComputationRelationship("rel_prod_markup_rate", PRODUCT_ID, "calc_prod_markup",
            "markup_rate_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_markup_rate),
        ComputationRelationship("rel_prod_markup_output", "calc_prod_markup", PRODUCT_ID,
            "markup_price_result", ComputationRelationType.OUTPUT_TO, "property", data_output=prod_markup_output),
    ])

    # --- Packaging Calculation ---
    relationships.extend([
        ComputationRelationship("rel_prod_markup_to_packaged", PRODUCT_ID, "calc_prod_packaged",
            "markup_price_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_markup_price),
        ComputationRelationship("rel_prod_packaging", PRODUCT_ID, "calc_prod_packaged",
            "packaging_cost_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_packaging_cost),
        ComputationRelationship("rel_prod_packaged_output", "calc_prod_packaged", PRODUCT_ID,
            "packaged_price_result", ComputationRelationType.OUTPUT_TO, "property", data_output=prod_packaged_output),
    ])

    # --- Shipping Calculation ---
    relationships.extend([
        ComputationRelationship("rel_prod_weight", PRODUCT_ID, "calc_prod_shipping",
            "weight_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_shipping_weight),
        ComputationRelationship("rel_prod_shipping_rate", PRODUCT_ID, "calc_prod_shipping",
            "shipping_rate_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_shipping_rate),
        ComputationRelationship("rel_prod_shipping_output", "calc_prod_shipping", PRODUCT_ID,
            "shipping_cost_result", ComputationRelationType.OUTPUT_TO, "property", data_output=prod_shipping_output),
    ])

    # --- Final Price Calculation ---
    relationships.extend([
        ComputationRelationship("rel_prod_packaged_to_final", PRODUCT_ID, "calc_prod_final",
            "packaged_price_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_packaged_price),
        ComputationRelationship("rel_prod_shipping_to_final", PRODUCT_ID, "calc_prod_final",
            "shipping_cost_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_shipping_cost),
        ComputationRelationship("rel_prod_tax_to_final", PRODUCT_ID, "calc_prod_final",
            "tax_rate_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_tax_rate),
        ComputationRelationship("rel_prod_final_output", "calc_prod_final", PRODUCT_ID,
            "final_price_result", ComputationRelationType.OUTPUT_TO, "property", data_output=prod_final_output),
    ])

    # --- Profit Margin Calculation ---
    relationships.extend([
        ComputationRelationship("rel_prod_final_to_profit", PRODUCT_ID, "calc_prod_profit",
            "final_price_price_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_final_price),
        ComputationRelationship("rel_prod_total_to_profit", PRODUCT_ID, "calc_prod_profit",
            "total_cost_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=prod_total_cost),
        ComputationRelationship("rel_prod_profit_output", "calc_prod_profit", PRODUCT_ID,
            "profit_margin_result", ComputationRelationType.OUTPUT_TO, "property", data_output=prod_profit_output),
    ])

    # Add all relationships to graph
    for rel in relationships:
        graph = graph.add_computation_relationship(rel)

    # ==================== Initial Data ====================

    node_data_map = {
        RAW_MATERIAL_A_ID: {
            "name": "Steel Rod",
            "material_type": "Metal",
            "base_cost": 10.0,
            "quantity": 5,
            "transport_cost": 2.0,
            "total_cost": 0.0,  # Computed: (base_cost + transport_cost) * quantity
        },
        RAW_MATERIAL_B_ID: {
            "name": "Plastic Granules",
            "material_type": "Polymer",
            "base_cost": 5.0,
            "quantity": 3,
            "transport_cost": 1.5,
            "total_cost": 0.0,  # Computed: (base_cost + transport_cost) * quantity
        },
        PART_X_ID: {
            "name": "Metal Frame",
            "part_type": "Structural",
            "assembly_cost": 15.0,
            "overhead_rate": 0.2,
            "material_a_cost": 0.0,  # From RM_A.total_cost
            "total_cost": 0.0,  # Computed: (material_a_cost + assembly) * (1 + overhead)
        },
        PART_Y_ID: {
            "name": "Plastic Housing",
            "part_type": "Cover",
            "assembly_cost": 8.0,
            "overhead_rate": 0.15,
            "material_b_cost": 0.0,  # From RM_B.total_cost
            "total_cost": 0.0,  # Computed: (material_b_cost + assembly) * (1 + overhead)
        },
        PRODUCT_ID: {
            "name": "Industrial Camera",
            "product_type": "Electronics",
            "assembly_cost": 25.0,
            "markup_rate": 0.5,
            "packaging_cost": 10.0,
            "shipping_weight": 2.5,
            "shipping_rate": 5.0,
            "tax_rate": 0.08,
            "part_x_cost": 0.0,  # From Part_X.total_cost
            "part_y_cost": 0.0,  # From Part_Y.total_cost
            "total_cost": 0.0,  # Computed: part_x + part_y + assembly
            "markup_price": 0.0,  # Computed: total_cost * (1 + markup)
            "packaged_price": 0.0,  # Computed: markup + packaging
            "shipping_cost": 0.0,  # Computed: weight * rate
            "final_retail_price": 0.0,  # Computed: (packaged + shipping) * (1 + tax)
            "profit_margin": 0.0,  # Computed: final - total_cost
        },
    }

    return graph, node_data_map


# ============================================================================
# NetworkX Graph Utilities
# ============================================================================

def build_networkx_graph(graph: ComputationGraph, node_data_map: dict) -> tuple[nx.DiGraph, nx.DiGraph]:
    """Build NetworkX graph from ComputationGraph and node data"""
    G = nx.DiGraph()

    # Add data nodes
    for node_id, node_data in node_data_map.items():
        G.add_node(node_id, **node_data)

    # Add computation nodes
    for node_id, node in graph.computation_nodes.items():
        G.add_node(
            node_id,
            name=node.name,
            code=node.code,
            engine=node.engine.value,
            is_computation=True,
        )

    # Add edges with property name mapping
    for rel in graph.computation_relationships.values():
        if rel.relation_type == ComputationRelationType.DEPENDS_ON:
            output_prop = rel.datasource.property_name if hasattr(rel, "datasource") and rel.datasource else None
            G.add_edge(rel.source_id, rel.target_id, relation_type="DEPENDS_ON", property_name=output_prop)
        elif rel.relation_type == ComputationRelationType.OUTPUT_TO:
            output_prop = rel.data_output.property_name if hasattr(rel, "data_output") and rel.data_output else None
            G.add_edge(rel.source_id, rel.target_id, relation_type="OUTPUT_TO", property_name=output_prop)

    # Create dependency-only graph for topological sort
    dep_graph = nx.DiGraph()
    dep_graph.add_nodes_from(G.nodes())
    dep_graph.add_edges_from([
        (source, target) for source, target, data in G.edges(data=True)
        if data.get("relation_type") == "DEPENDS_ON"
    ])

    return G, dep_graph


def execute_networkx_graph(G: nx.DiGraph, dep_graph: nx.DiGraph, verbose: bool = True) -> list | None:
    """Execute computations in topological order"""
    try:
        order = list(nx.topological_sort(dep_graph))
        if verbose:
            print(f"Execution order: {' -> '.join(order)}")
            print()
    except nx.NetworkXError as e:
        if verbose:
            print(f"Error: Graph contains {e}")
        return None

    # Map cross-node property propagation: (target_node_id, property_name) -> source_node_id
    # For example: part_x.material_a_cost should get value from raw_material_a.total_cost
    cross_prop_map = {
        (PART_X_ID, "material_a_cost"): RAW_MATERIAL_A_ID,
        (PART_Y_ID, "material_b_cost"): RAW_MATERIAL_B_ID,
        (PRODUCT_ID, "part_x_cost"): PART_X_ID,
        (PRODUCT_ID, "part_y_cost"): PART_Y_ID,
    }

    for node_id in order:
        node_data = G.nodes[node_id]

        if node_data.get("is_computation"):
            if verbose:
                print(f"Executing: {node_id} ({node_data.get('name')})")
                print(f"  Code: {node_data.get('code')}")

            # Gather input variables from all predecessors
            variables = {}
            for predecessor in dep_graph.predecessors(node_id):
                # Get all properties from predecessor node
                for prop_name, prop_value in G.nodes[predecessor].items():
                    if not prop_name.startswith('_'):
                        variables[prop_name] = prop_value

            if verbose and variables:
                print(f"  Variables: {variables}")

            # Execute computation
            code = node_data.get("code", "")
            try:
                result = eval(code, {}, variables)
                if verbose:
                    print(f"  Result: {result}")

                # Update successors via OUTPUT_TO edges
                for successor in G.successors(node_id):
                    edge_data = G.edges[node_id, successor]
                    if edge_data.get("relation_type") == "OUTPUT_TO":
                        property_name = edge_data.get("property_name")
                        if property_name:
                            G.nodes[successor][property_name] = result
                            if verbose:
                                print(f"  -> Updated {successor}.{property_name} = {result}")

                            # Handle cross-node property propagation
                            for (target_node, prop), source_node in cross_prop_map.items():
                                if successor == source_node and prop == property_name:
                                    # Propagate to target node
                                    if target_node in G.nodes:
                                        G.nodes[target_node][prop] = result
                                        if verbose:
                                            print(f"  -> Propagated to {target_node}.{prop} = {result}")
            except Exception as e:
                if verbose:
                    print(f"  Error: {e}")

            if verbose:
                print()

    return order


# ============================================================================
# Neo4j Utilities
# ============================================================================

async def create_all_data_nodes(data_provider: Neo4jDataProvider, node_data_map: dict) -> dict:
    """Create all data nodes in Neo4j"""
    neo4j_id_map = {}
    for node_id, node_data in node_data_map.items():
        node_type = "Product" if "product_type" in node_data else ("Part" if "part_type" in node_data else "RawMaterial")
        neo4j_id = await data_provider.create_node(node_type, node_data)
        neo4j_id_map[node_id] = neo4j_id
    return neo4j_id_map


# ============================================================================
# Display Utilities
# ============================================================================

def print_header(title: str, width: int = 80):
    """Print section header"""
    print("=" * width)
    print(title)
    print("=" * width)
    print()


def print_separator(char: str = "-", count: int = 40):
    """Print section separator"""
    print(char * count)


def print_node_data(node_id: str, node_data: dict, indent: str = "  "):
    """Print node data properties"""
    print(f"{node_id}:")
    for key, value in {k: v for k, v in node_data.items() if not k.startswith('_')}.items():
        print(f"{indent}- {key}: {value}")


def print_supply_chain_summary(G: nx.DiGraph):
    """Print supply chain summary with{computed results"""
    print("=" * 80)
    print("SUPPLY CHAIN SUMMARY")
    print("=" * 80)
    print()

    # Raw Materials
    print("Raw Materials:")
    for node_id in [RAW_MATERIAL_A_ID, RAW_MATERIAL_B_ID]:
        data = G.nodes[node_id]
        print(f"  - {data.get('name', node_id)}")
        print(f"    Base Cost: {data.get('base_cost', 'N/A')}, Qty: {data.get('quantity', 'N/A')}")
        print(f"    Transport Cost: {data.get('transport_cost', 'N/A')}")
        print(f"    Total Cost: {data.get('total_cost', 'N/A')}")
        print()

    # Parts
    print("Parts:")
    for node_id in [PART_X_ID, PART_Y_ID]:
        data = G.nodes[node_id]
        print(f"  - {data.get('name', node_id)}")
        print(f"    Assembly Cost: {data.get('assembly_cost', 'N/A')}")
        print(f"    Overhead Rate: {data.get('overhead_rate', 'N/A')}")
        print(f"    Material Cost: {data.get('material_a_cost', 'N/A') if 'material_a_cost' in data else data.get('material_b_cost', 'N/A')}")
        print(f"    Total Cost: {data.get('total_cost', 'N/A')}")
        print()

    # Final Product
    data = G.nodes[PRODUCT_ID]
    print(f"Final Product: {data.get('name', 'Unknown')}")
    print()
    print("Base Costs:")
    print(f"  - Part X Cost: {data.get('part_x_cost', 'N/A')}")
    print(f"  - Part Y Cost: {data.get('part_y_cost', 'N/A')}")
    print(f"  - Assembly Cost: {data.get('assembly_cost', 'N/A')}")
    print()
    print("Pricing Chain:")
    print(f"  - Total Cost: {data.get('total_cost', 'N/A')}")
    print(f"  - Markup Price: {data.get('markup_price', 'N/A')}")
    print(f"  - Packaged Price: {data.get('packaged_price', 'N/A')}")
    print(f"  - Shipping Cost: {data.get('shipping_cost', 'N/A')}")
    print(f"  - Final Retail Price: {data.get('final_retail_price', 'N/A')}")
    print(f"  - Profit Margin: {data.get('profit_margin', 'N/A')}")
    print()


def print_graph_structure(G: nx.DiGraph):
    """Print graph structure overview"""
    print()
    print("Graph Structure:")
    print()
    print("Data Nodes:")
    for node_id, data in G.nodes(data=True):
        if not data.get("is_computation"):
            print(f"  - {node_id} ({data.get('name', 'Unknown')})")

    print()
    print("Computation Nodes:")
    for node_id, data in G.nodes(data=True):
        if data.get("is_computation"):
            print(f"  - {node_id}: {data.get('code')}")

    print()
    print("Total:")
    print(f"  - {sum(1 for _, d in G.nodes(data=True) if not d.get('is_computation'))} data nodes")
    print(f"  - {sum(1 for _, d in G.nodes(data=True) if d.get('is_computation'))} computation nodes")
    print(f"  - {G.number_of_edges()} edges")
    print()


# ============================================================================
# Demo Functions
# ============================================================================

async def demo_with_neo4j():
    """Demo using Neo4j with full graph creation and execution"""
    print_header("Supply Chain Demo with Neo4j")
    print(f"Neo4j: {NEO4J_URI}")
    print()

    try:
        data_provider = Neo4jDataProvider(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
        print("Connecting to Neo4j...")
        print()

        # Step 1: Build graph and create data nodes
        print_header("Step 1: Build Computation Graph and Create Data Nodes")
        graph, node_data_map = build_supply_chain_graph()

        print("Creating data nodes:")
        neo4j_id_map = await create_all_data_nodes(data_provider, node_data_map)
        for node_id, neo4j_id in neo4j_id_map.items():
            print(f"  - {node_id} -> Neo4j ID: {neo4j_id}")
        print()

        # Step 2: Create computation nodes
        print_header("Step 2: Create Computation Nodes")
        comp_node_id_map = {}
        for node_id, node in graph.computation_nodes.items():
            neo4j_id = await data_provider.create_node(
                "ComputationNode",
                {
                    "id": node.id,
                    "name": node.name,
                    "code": node.code,
                    "engine": node.engine.value,
                    "graph_id": graph.id,
                }
            )
            comp_node_id_map[node_id] = neo4j_id
        print(f"Created {len(comp_node_id_map)} computation nodes")
        print()

        # Step 3: Create relationships
        print_header("Step 3: Create Relationships")
        rel_count = 0
        for rel in graph.computation_relationships.values():
            source_id = (neo4j_id_map.get(rel.source_id) if rel.source_id in neo4j_id_map
                        else comp_node_id_map.get(rel.source_id))
            target_id = (comp_node_id_map.get(rel.target_id) if rel.relation_type == ComputationRelationType.DEPENDS_ON
                        else neo4j_id_map.get(rel.target_id))

            if source_id and target_id:
                rel_props = {
                    "id": rel.id,
                    "name": rel.name,
                    "relation_type": rel.relation_type.value,
                    "graph_id": graph.id,
                }
                await data_provider.create_relationship(source_id, target_id, rel.relation_type.value, rel_props)
                rel_count += 1
        print(f"Created {rel_count} relationships")
        print()

        # Step 4: Execute computations
        print_header("Step 4: Execute Computations")
        executor = ComputationExecutor(data_provider)

        results = {}
        for data_node_id in neo4j_id_map.values():
            node_results = await executor.execute_and_write_back(graph=graph, start_node_id=data_node_id)
            results.update(node_results)

        print("Computation Results:")
        for node_id, outputs in results.items():
            node = graph.computation_nodes.get(node_id)
            name = node.name if node else node_id
            print(f"  - {name}: {outputs}")
        print()

        await data_provider.close()
        print("Neo4j connection closed")

    except Exception as e:
        print(f"Error: {e}")
        print("\nTip: Make sure Neo4j is running")
        print("Start: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/neo4j neo4j")


async def demo_with_networkx():
    """Demo using NetworkX for in-memory computation with What-If analysis"""
    print_header("Supply Chain Demo with NetworkX (What-If Analysis)")
    print(f"Neo4j: {NEO4J_URI} (for initial data read)")
    print()

    try:
        # Step 1: Build graph
        print_header("Step 1: Build Supply Chain Graph")
        graph, node_data_map = build_supply_chain_graph()

        print("Initial Data:")
        for node_id, data in node_data_map.items():
            print_node_data(node_id, data, indent="    ")
        print()

        # Step 2: Build NetworkX graph
        print_header("Step 2: Build NetworkX Graph")
        G, dep_graph = build_networkx_graph(graph, node_data_map)
        print_graph_structure(G)

        # Step 3: Execute initial computation
        print_header("Step 3: Execute Initial Computation")
        order = execute_networkx_graph(G, dep_graph)
        if order is None:
            return

        print_supply_chain_summary(G)

        # Step 4: What-If Simulation 1 - Increase Raw Material A cost
        print_header("Step 4: What-If - Raw Material A Cost Increase")
        print("Scenario: Steel Rod base cost increases from $10 to $15 (+50%)")
        print()

        original_cost = G.nodes[RAW_MATERIAL_A_ID]["base_cost"]
        G.nodes[RAW_MATERIAL_A_ID]["base_cost"] = 15.0

        print("Re-executing computation...")
        execute_networkx_graph(G, dep_graph, verbose=False)

        print_supply_chain_summary(G)
        print("Impact Analysis:")
        print(f"  - Raw Material A total cost increased from $60.00 to ${G.nodes[RAW_MATERIAL_A_ID]['total_cost']:.2f}")

        # Step 5: What-If Simulation 2 - Reduce shipping rate
        print_header("Step 5: What-If - Shipping Rate Reduction")
        print("Scenario: Negotiate better shipping rate from $5 to $3 per kg")
        print()

        # Restore RM_A cost for this simulation
        G.nodes[RAW_MATERIAL_A_ID]["base_cost"] = original_cost
        G.nodes[PRODUCT_ID]["shipping_rate"] = 3.0

        print("Re-executing computation...")
        execute_networkx_graph(G, dep_graph, verbose=False)

        print_supply_chain_summary(G)
        print("Impact Analysis:")
        print(f"  - Shipping cost reduced from $12.50 to $7.50")
        print(f"  - Final retail price reduced")

        # Step 6: What-If Simulation 3 - Adjust markup rate
        print_header("Step 6: What-If - Markup Rate Adjustment")
        print("Scenario: Increase markup{from 50% to 70% for higher margin")
        print()

        # Restore shipping rate
        G.nodes[PRODUCT_ID]["shipping_rate"] = 5.0
        # Increase markup
        G.nodes[PRODUCT_ID]["markup_rate"] = 0.7

        print("Re-executing computation...")
        execute_networkx_graph(G, dep_graph, verbose=False)

        print_supply_chain_summary(G)
        profit_margin = G.nodes[PRODUCT_ID]["profit_margin"]
        total_cost = G.nodes[PRODUCT_ID]["total_cost"]
        if total_cost > 0:
            print("Impact Analysis:")
            print(f"  - New profit margin: ${profit_margin:.2f}")
            print(f"  - New profit percentage: {(profit_margin / total_cost * 100):.1f}%")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point with demo mode selection"""
    print("Supply Chain Computation Graph Demo")
    print("=" * 80)
    print()
    print("Choose demo mode:")
    print("  1 - Neo4j Demo (create graph, execute, write to database)")
    print("  2 - NetworkX Demo (in-memory with What-If analysis)")
    print("  3 - Both")
    print()

    choice = "1"  # Default: NetworkX demo

    if choice == "1":
        await demo_with_neo4j()
    elif choice == "2":
        await demo_with_networkx()
    elif choice == "3":
        await demo_with_neo4j()
        print()
        await demo_with_networkx()

    print()
    print_header("Demo Completed!")
    print()
    print("Graph Structure:")
    print("  5 Data Nodes: 2 Raw Materials + 2 Parts + 1 Final Product")
    print("  10 Computation Nodes:")
    print("    - calc_rm_a_total, calc_rm_b_total")
    print("    - calc_part_x_total, calc_part_yy_total")
    print("    - calc_prod_total, calc_prod_markup, calc_prod_packaged")
    print("    - calc_prod_shipping, calc_prod_final, calc_prod_profit")
    print()
    print("Computation Flow:")
    print("  1. Raw Materials: (base_cost + transport) * quantity")
    print("  2. Parts: (material_cost + assembly) * (1 + overhead)")
    print("  3. Product: part_x + part_y + assembly")
    print("  4. Markup: total_cost * (1 + markup_rate)")
    print("  5. Packaging: markup_price + packaging_cost")
    print("  6. Shipping: weight * shipping_rate")
    print("  7. Final: (packaged + shipping) * (1 + tax)")
    print("  8. Profit: final_price - total_cost")
    print()
    print("Cross-Node Dependencies:")
    print("  - Part X depends on Raw Material A total cost")
    print("  - Part Y depends on Raw Material B total cost")
    print("  - Product depends on Part X and Part Y total costs")


if __name__ == "__main__":
    asyncio.run(main())
