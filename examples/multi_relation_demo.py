"""
Multi-Relation Computation Graph Demo

Demonstrates ComputationNode connecting to different properties of the same data node
using multiple relationship types (DEPENDS_ON and OUTPUT_TO).
"""

import asyncio
import logging
import sys
from pathlib import Path
import networkx as nx
import pickle

logger = logging.getLogger(__name__)

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
from domain.services import Neo4jDataProvider

# ============================================================================
# Constants and Configuration
# ============================================================================

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"
PRODUCT_NODE_ID = "product_001"

# Output property names for writing back to Neo4j
OUTPUT_PROPERTIES = ["total_output", "price_after_discount", "final_price"]

# ============================================================================
# Graph Construction
# ============================================================================

def build_multi_relation_graph() -> tuple[ComputationGraph, dict]:
    """Build a computation graph with multiple relationships to same data node

    Returns:
        (graph, node_data_map) - graph definition and initial node data
    """
    # Input specifications
    price_input = InputSpec("property", "Product", "price")
    quantity_input = InputSpec("property", "Product", "quantity")
    discount_rate_input = InputSpec("property", "Product", "discount_rate")
    tax_rate_input = InputSpec("property", "Product", "tax_rate")

    # Output specifications
    total_output = OutputSpec("property", "Product", "total_output")
    price_after_discount_output = OutputSpec("property", "Product", "price_after_discount")
    final_price_output = OutputSpec("property", "Product", "final_price")

    # Computation nodes
    calc_total = ComputationNode(
        id="calc_total",
        name="calculate_total_price",
        level=ComputationLevel.PROPERTY,
        inputs=(price_input, quantity_input),
        outputs=(total_output,),
        code="price * quantity",
        engine=ComputationEngine.PYTHON,
    )

    calc_discount = ComputationNode(
        id="calc_discount",
        name="apply_discount",
        level=ComputationLevel.PROPERTY,
        inputs=(total_output, discount_rate_input),
        outputs=(price_after_discount_output,),
        code="total_output * (1 - discount_rate)",
        engine=ComputationEngine.PYTHON,
    )

    calc_tax = ComputationNode(
        id="calc_tax",
        name="calculate_final_price",
        level=ComputationLevel.PROPERTY,
        inputs=(price_after_discount_output, tax_rate_input),
        outputs=(final_price_output,),
        code="price_after_discount * (1 + tax_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # Build computation relationships
    relationships = [
        # calc_total dependencies
        ComputationRelationship("rel_price_to_calc_total", PRODUCT_NODE_ID, "calc_total",
            "price_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=price_input),
        ComputationRelationship("rel_quantity_to_calc_total", PRODUCT_NODE_ID, "calc_total",
            "quantity_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=quantity_input),
        ComputationRelationship("rel_calc_total_to_total_output", "calc_total", PRODUCT_NODE_ID,
            "total_output_result", ComputationRelationType.OUTPUT_TO, "property", data_output=total_output),

        # calc_discount dependencies
        ComputationRelationship("rel_total_output_to_calc_discount", PRODUCT_NODE_ID, "calc_discount",
            "total_output_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=total_output),
        ComputationRelationship("rel_discount_rate_to_calc_discount", PRODUCT_NODE_ID, "calc_discount",
            "discount_rate_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=discount_rate_input),
        ComputationRelationship("rel_calc_discount_to_price_after_discount", "calc_discount", PRODUCT_NODE_ID,
            "price_after_discount_result", ComputationRelationType.OUTPUT_TO, "property", data_output=price_after_discount_output),

        # calc_tax dependencies
        ComputationRelationship("rel_price_after_discount_to_calc_tax", PRODUCT_NODE_ID, "calc_tax",
            "price_after_discount_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=price_after_discount_output),
        ComputationRelationship("rel_tax_rate_to_calc_tax", PRODUCT_NODE_ID, "calc_tax",
            "tax_rate_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=tax_rate_input),
        ComputationRelationship("rel_calc_tax_to_final_price", "calc_tax", PRODUCT_NODE_ID,
            "final_price_result", ComputationRelationType.OUTPUT_TO, "property", data_output=final_price_output),
    ]

    # Build graph
    graph = ComputationGraph(id="multi_relation_computation_graph")
    for node in [calc_total, calc_discount, calc_tax]:
        graph = graph.add_computation_node(node)
    for rel in relationships:
        graph = graph.add_computation_relationship(rel)

    # Initial data
    node_data_map = {
        PRODUCT_NODE_ID: {
            "name": "iPhone 15 Pro",
            "model": "A3102",
            "category": "Smartphone",
            "price": 100.0,
            "quantity": 2,
            "discount_rate": 0.1,
            "tax_rate": 0.08,
        },
    }

    return graph, node_data_map


# ============================================================================
# NetworkX Graph Utilities
# ============================================================================

def build_networkx_graph(graph: ComputationGraph, node_data_map: dict) -> tuple[nx.DiGraph, nx.DiGraph]:
    """Build NetworkX graph from ComputationGraph and node data

    Returns:
        (graph, dep_graph) - full graph and dependency-only graph for topological sort
    """
    G = nx.DiGraph()

    # Add data node
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
            priority=node.priority,
        )

    # Add edges with property name mapping
    for rel in graph.computation_relationships.values():
        if rel.relation_type == ComputationRelationType.DEPENDS_ON:
            output_prop = rel.datasource.property_name if hasattr(rel, "datasource") and rel.datasource else None
            G.add_edge(rel.source_id, rel.target_id, relation_type="DEPENDS_ON", property_name=output_prop)
        elif rel.relation_type == ComputationRelationType.OUTPUT_TO:
            output_prop = rel.data_output.property_name if hasattr(rel, "data_output") and rel.data_output else None
            G.add_edge(rel.source_id, rel.target_id, relation_type="OUTPUT_TO", property_name=output_prop)

    # Create dependency graph: DEPENDS_ON (data->comp) + writer->reader (comp->comp)
    dep_graph = nx.DiGraph()
    dep_graph.add_nodes_from(G.nodes())
    dep_graph.add_edges_from([
        (source, target) for source, target, data in G.edges(data=True)
        if data.get("relation_type") == "DEPENDS_ON"
    ])
    outputs = [(rel.source_id, rel.target_id, rel.data_output.property_name)
               for rel in graph.computation_relationships.values()
               if rel.relation_type == ComputationRelationType.OUTPUT_TO and getattr(rel, "data_output", None)]
    reads = [(rel.source_id, rel.target_id, rel.datasource.property_name)
             for rel in graph.computation_relationships.values()
             if rel.relation_type == ComputationRelationType.DEPENDS_ON and getattr(rel, "datasource", None)]
    for (writer, data_node, prop) in outputs:
        for (dn, reader, read_prop) in reads:
            if data_node == dn and prop == read_prop and writer != reader:
                dep_graph.add_edge(writer, reader)

    return G, dep_graph


def execute_networkx_graph(G: nx.DiGraph, dep_graph: nx.DiGraph, verbose: bool = True) -> list | None:
    """Execute computations in topological order

    Args:
        G: Full NetworkX graph with nodes and edges
        dep_graph: Dependency-only graph for topological sort
        verbose: Print execution details

    Returns:
        Topological order if successful, None if graph has cycle
    """
    try:
        key = lambda n: (G.nodes[n].get("priority", 0), n)
        order = list(nx.lexicographical_topological_sort(dep_graph, key=key))
        if verbose:
            logger.info("Execution order: %s", " -> ".join(order))
            logger.info("")
    except nx.NetworkXError as e:
        if verbose:
            logger.error("Graph contains a cycle: %s", e)
        return None

    for node_id in order:
        node_data = G.nodes[node_id]

        if node_data.get("is_computation"):
            if verbose:
                logger.info("Executing: %s (%s)", node_id, node_data.get('name'))
                logger.info("  Code: %s", node_data.get('code'))

            # Gather input variables from predecessors
            variables = {}
            for predecessor in G.predecessors(node_id):
                variables.update(G.nodes[predecessor])

            # Execute computation
            code = node_data.get("code", "")
            try:
                result = eval(code, {}, variables)
                if verbose:
                    logger.info("  Result: %s", result)

                # Update successors via OUTPUT_TO edges
                for successor in G.successors(node_id):
                    edge_data = G.edges[node_id, successor]
                    if edge_data.get("relation_type") == "OUTPUT_TO":
                        property_name = edge_data.get("property_name")
                        if property_name:
                            G.nodes[successor][property_name] = result
                            if verbose:
                                logger.info("  -> Updated %s.%s = %s", successor, property_name, result)
            except Exception as e:
                if verbose:
                    logger.error("  Error: %s", e)

            if verbose:
                logger.info("")

    return order


# ============================================================================
# Neo4j Utilities
# ============================================================================

def get_connection_info() -> str:
    """Return formatted connection info string"""
    return f"""
Neo4j connection config:
  URI: {NEO4J_URI}
  User: {NEO4J_USER}
"""


async def get_or_create_product_node(data_provider: Neo4jDataProvider, node_data: dict) -> tuple[str, dict]:
    """Get existing product node or create new one

    Returns:
        (node_id, node_data) - Neo4j node ID and associated data
    """
    driver = data_provider._get_driver()
    if driver is None:
        return await data_provider.create_node("Product", node_data), node_data

    async with driver.session() as session:
        query = "MATCH (n:Product {name: $name}) RETURN elementId(n) AS node_id, n"
        result = await session.run(query, name=node_data["name"])
        record = await result.single()

        if record:
            return record["node_id"], dict(record["n"])

    return await data_provider.create_node("Product", node_data), node_data


async def write_output_properties(data_provider: Neo4jDataProvider, node_id: str,
                                   node_data: dict, properties: list | None = None) -> bool:
    """Write computed output properties to Neo4j

    Args:
        data_provider: Neo4j data provider
        node_id: Target node ID
        node_data: Source node data dictionary
        properties: List of property names to write (default: OUTPUT_PROPERTIES)

    Returns:
        Success status
    """
    if properties is None:
        properties = OUTPUT_PROPERTIES

    output_props = {prop: node_data.get(prop) for prop in properties}
    return await data_provider.set_node_properties(node_id, output_props)


async def verify_node_data(driver, node_id: str) -> dict | None:
    """Verify and retrieve node data from Neo4j

    Returns:
        Node data dictionary or None
    """
    async with driver.session() as session:
        query = "MATCH (n:Product) WHERE elementId(n) = $node_id RETURN n"
        result = await session.run(query, node_id=node_id)
        record = await result.single()
        return dict(record["n"]) if record else None


# ============================================================================
# Display Utilities
# ============================================================================

def print_header(title: str, width: int = 80):
    """Log section header"""
    logger.info("=" * width)
    logger.info(title)
    logger.info("=" * width)
    logger.info("")


def print_separator(char: str = "-", count: int = 40):
    """Log section separator"""
    logger.info(char * count)


def print_node_data(node_data: dict, indent: str = "  "):
    """Log node data properties"""
    for key, value in node_data.items():
        logger.info("%s- %s: %s", indent, key, value)


def print_product_summary(data: dict):
    """Log product summary with inputs and computed outputs"""
    logger.info("Product: %s", data.get('name', 'Unknown'))
    logger.info("")
    logger.info("Original Inputs:")
    logger.info("  - Price: %s", data.get('price', 'N/A'))
    logger.info("  - Quantity: %s", data.get('quantity', 'N/A'))
    logger.info("  - Discount Rate: %s", data.get('discount_rate', 'N/A'))
    logger.info("  - Tax Rate: %s", data.get('tax_rate', 'N/A'))
    logger.info("")
    logger.info("Computed Outputs:")
    logger.info("  - Total Output: %s", data.get('total_output', 'N/A'))
    logger.info("  - Price After Discount: %s", data.get('price_after_discount', 'N/A'))
    logger.info("  - Final Price: %s", data.get('final_price', 'N/A'))


def print_graph_structure(G: nx.DiGraph, data_node_id: str = PRODUCT_NODE_ID):
    """Log NetworkX graph structure"""
    logger.info("Data Node:")
    node_data = G.nodes[data_node_id]
    logger.info("  - %s", data_node_id)
    for key, value in node_data.items():
        logger.info("    %s: %s", key, value)

    logger.info("Computation Nodes:")
    for node_id, data in G.nodes(data=True):
        if data.get("is_computation"):
            logger.info("  - %s (%s)", node_id, data.get('name'))
            logger.info("    Code: %s", data.get('code'))

    logger.info("Edges:")
    for source, target, data in G.edges(data=True):
        logger.info("  - %s -> %s (%s)", source, target, data.get('relation_type'))


# ============================================================================
# Demo Functions
# ============================================================================

async def demo_with_networkx():
    """Demo using NetworkX for graph computation with topological sort, reading from Neo4j"""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print_header("NetworkX-Based Computation Graph Demo (Neo4j Read-Only)")
    logger.info("%s", get_connection_info())

    try:
        data_provider = Neo4jDataProvider(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
        logger.info("Connecting to Neo4j...")
        logger.info("")

        # Step 1: Read data from Neo4j
        print_header("Step 1: Read Data from Neo4j")
        graph, node_data_map = build_multi_relation_graph()

        product_neo4j_id, product_data = await get_or_create_product_node(
            data_provider, node_data_map[PRODUCT_NODE_ID]
        )
        logger.info("%s product node with ID: %s", "Found existing" if product_data else "Created new", product_neo4j_id)
        logger.info("")
        logger.info("Product data:")
        print_node_data(product_data)
        logger.info("")

        await data_provider.close()
        logger.info("Neo4j connection closed (computations will run in memory)")
        logger.info("")

        # Step 2: Build NetworkX graph
        print_header("Step 2: Build NetworkX Graph")
        print_separator()
        G, dep_graph = build_networkx_graph(graph, {PRODUCT_NODE_ID: product_data})
        logger.info("  Added %s computation nodes", len(graph.computation_nodes))
        logger.info("  Added %s edges", len(graph.computation_relationships))
        logger.info("")

        # Step 3: Display graph structure
        print_header("Step 3: Display Graph Structure")
        print_separator()
        print_graph_structure(G)
        logger.info("")

        # Step 4: Execute computations
        print_header("Step 4: Execute Computations (Topological Sort)")
        order = execute_networkx_graph(G, dep_graph)
        if order is None:
            return

        # Step 5: Display results
        print_header("Step 5: Computed Results")
        logger.info("Computed output values:")
        for prop in OUTPUT_PROPERTIES:
            logger.info("  - %s: %s", prop.replace('_', ' ').title(), G.nodes[PRODUCT_NODE_ID].get(prop, 'N/A'))
        logger.info("")

        with open("graph.pkl", "wb") as f:
            pickle.dump(G, f)

        # 从磁盘读取
        with open("graph.pkl", "rb") as f:
            G = pickle.load(f)

        # Step 6: What-If Simulation 1 - Price increase
        print_header("Step 6: What-If Simulation - Price Increase")
        logger.info("--- What-If: What if price increases from 100.0 to 150.0? ---")
        logger.info("")

        original_price = G.nodes[PRODUCT_NODE_ID]["price"]
        G.nodes[PRODUCT_NODE_ID]["price"] = 150.0

        execute_networkx_graph(G, dep_graph, verbose=False)

        logger.info("New Computed Values:")
        for prop in OUTPUT_PROPERTIES:
            logger.info("  - %s: %s", prop.replace('_', ' ').title(), G.nodes[PRODUCT_NODE_ID].get(prop, 'N/A'))
        logger.info("")

        # Restore for next simulation
        G.nodes[PRODUCT_NODE_ID]["price"] = original_price

        # Step 7: What-If Simulation 2 - Quantity increase
        print_header("Step 7: What-If Simulation - Quantity Increase")
        logger.info("--- What-If: What if quantity increases from 2 to 10? ---")
        logger.info("")

        original_quantity = G.nodes[PRODUCT_NODE_ID]["quantity"]
        G.nodes[PRODUCT_NODE_ID]["quantity"] = 10

        execute_networkx_graph(G, dep_graph, verbose=False)

        logger.info("New Computed Values:")
        for prop in OUTPUT_PROPERTIES:
            logger.info("  - %s: %s", prop.replace('_', ' ').title(), G.nodes[PRODUCT_NODE_ID].get(prop, 'N/A'))
        logger.info("")

    except Exception as e:
        logger.error("Error: %s", e)
        logger.info("Tip: Please make sure Neo4j database is running")
        logger.info("Start Neo4j: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/neo4j neo4j")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point: NetworkX-based computation graph with Neo4j read/write."""
    await demo_with_networkx()
    logger.info("")
    print_header("Demo completed!")
    logger.info("Graph structure:")
    logger.info("  Data Node: Product (iPhone 15 Pro)")
    logger.info("")
    logger.info("Computation Nodes:")
    logger.info("  - calc_total: price * quantity")
    logger.info("  - calc_discount: total_output * (1 - discount_rate)")
    logger.info("  - calc_tax: price_after_discount * (1 + tax_rate)")
    logger.info("")
    logger.info("Relationships (DEPENDS_ON: Data Node -> Computation Node):")
    logger.info("  - Product.price -> calc_total")
    logger.info("  - Product.quantity -> calc_total")
    logger.info("")
    logger.info("Relationships (OUTPUT_TO: Computation Node -> Data Node):")
    logger.info("  - calc_total -> Product.total_output")
    logger.info("  - calc_discount -> Product.price_after_discount")
    logger.info("  - calc_tax -> Product.final_price")
    logger.info("")
    logger.info("View graph in Neo4j Browser at: http://localhost:7474")


if __name__ == "__main__":
    asyncio.run(main())

# 是否写回数据库
# 自动生成计算图
# 图落盘