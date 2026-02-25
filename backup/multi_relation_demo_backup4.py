"""
Multi-Relation Computation Graph Demo

Demonstrates ComputationNode connecting to different properties of the same data node
using multiple relationship types (DEPENDS_ON and OUTPUT_TO).
"""

import asyncio
import sys
from pathlib import Path
import networkx as nx
import pickle

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
from domain.services.computation_executor import create_neo4j_data_provider

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
    """Execute computations in topological order

    Args:
        G: Full NetworkX graph with nodes and edges
        dep_graph: Dependency-only graph for topological sort
        verbose: Print execution details

    Returns:
        Topological order if successful, None if graph has cycle
    """
    try:
        order = list(nx.topological_sort(dep_graph))
        if verbose:
            print(f"Execution order: {' -> '.join(order)}")
            print()
    except nx.NetworkXError as e:
        if verbose:
            print(f"Error: Graph contains a cycle - {e}")
        return None

    for node_id in order:
        node_data = G.nodes[node_id]

        if node_data.get("is_computation"):
            if verbose:
                print(f"Executing: {node_id} ({node_data.get('name')})")
                print(f"  Code: {node_data.get('code')}")

            # Gather input variables from predecessors
            variables = {}
            for predecessor in G.predecessors(node_id):
                variables.update(G.nodes[predecessor])

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
            except Exception as e:
                if verbose:
                    print(f"  Error: {e}")

            if verbose:
                print()

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
    """Print section header"""
    print("=" * width)
    print(title)
    print("=" * width)
    print()


def print_separator(char: str = "-", count: int = 40):
    """Print section separator"""
    print(char * count)


def print_node_data(node_data: dict, indent: str = "  "):
    """Print node data properties"""
    for key, value in node_data.items():
        print(f"{indent}- {key}: {value}")


def print_product_summary(data: dict):
    """Print product summary with inputs and computed outputs"""
    print(f"Product: {data.get('name', 'Unknown')}")
    print()
    print("Original Inputs:")
    print(f"  - Price: {data.get('price', 'N/A')}")
    print(f"  - Quantity: {data.get('quantity', 'N/A')}")
    print(f"  - Discount Rate: {data.get('discount_rate', 'N/A')}")
    print(f"  - Tax Rate: {data.get('tax_rate', 'N/A')}")
    print()
    print("Computed Outputs:")
    print(f"  - Total Output: {data.get('total_output', 'N/A')}")
    print(f"  - Price After Discount: {data.get('price_after_discount', 'N/A')}")
    print(f"  - Final Price: {data.get('final_price', 'N/A')}")


def print_graph_structure(G: nx.DiGraph, data_node_id: str = PRODUCT_NODE_ID):
    """Print NetworkX graph structure"""
    print("\nData Node:")
    node_data = G.nodes[data_node_id]
    print(f"  - {data_node_id}")
    for key, value in node_data.items():
        print(f"    {key}: {value}")

    print("\nComputation Nodes:")
    for node_id, data in G.nodes(data=True):
        if data.get("is_computation"):
            print(f"  - {node_id} ({data.get('name')})")
            print(f"    Code: {data.get('code')}")

    print("\nEdges:")
    for source, target, data in G.edges(data=True):
        print(f"  - {source} -> {target} ({data.get('relation_type')})")


# ============================================================================
# Demo Functions
# ============================================================================

async def demo_with_networkx():
    """Demo using NetworkX for graph computation with topological sort, reading from Neo4j"""
    print_header("NetworkX-Based Computation Graph Demo (Neo4j Read-Only)")
    print(get_connection_info())

    try:
        data_provider = Neo4jDataProvider(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
        print("Connecting to Neo4j...")
        print()

        # Step 1: Read data from Neo4j
        print_header("Step 1: Read Data from Neo4j")
        graph, node_data_map = build_multi_relation_graph()

        product_neo4j_id, product_data = await get_or_create_product_node(
            data_provider, node_data_map[PRODUCT_NODE_ID]
        )
        print(f"{'Found existing' if product_data else 'Created new'} product node with ID: {product_neo4j_id}")
        print()
        print("Product data:")
        print_node_data(product_data)
        print()

        await data_provider.close()
        print("Neo4j connection closed (computations will run in memory)")
        print()

        # Step 2: Build NetworkX graph
        print_header("Step 2: Build NetworkX Graph")
        print_separator()
        G, dep_graph = build_networkx_graph(graph, {PRODUCT_NODE_ID: product_data})
        print(f"  Added {len(graph.computation_nodes)} computation nodes")
        print(f"  Added {len(graph.computation_relationships)} edges")
        print()

        # Step 3: Display graph structure
        print_header("Step 3: Display Graph Structure")
        print_separator()
        print_graph_structure(G)
        print()

        # Step 4: Execute computations
        print_header("Step 4: Execute Computations (Topological Sort)")
        order = execute_networkx_graph(G, dep_graph)
        if order is None:
            return

        # Step 5: Display results
        print_header("Step 5: Computed Results")
        print("Computed output values:")
        for prop in OUTPUT_PROPERTIES:
            print(f"  - {prop.replace('_', ' ').title()}: {G.nodes[PRODUCT_NODE_ID].get(prop, 'N/A')}")
        print()
        
        with open("graph.pkl", "wb") as f:
            pickle.dump(G, f)

        # 从磁盘读取
        with open("graph.pkl", "rb") as f:
            G = pickle.load(f)

        # Step 6: What-If Simulation 1 - Price increase
        print_header("Step 6: What-If Simulation - Price Increase")
        print("\n--- What-If: What if price increases from 100.0 to 150.0? ---")

        original_price = G.nodes[PRODUCT_NODE_ID]["price"]
        G.nodes[PRODUCT_NODE_ID]["price"] = 150.0

        print()
        execute_networkx_graph(G, dep_graph, verbose=False)

        print("New Computed Values:")
        for prop in OUTPUT_PROPERTIES:
            print(f"  - {prop.replace('_', ' ').title()}: {G.nodes[PRODUCT_NODE_ID].get(prop, 'N/A')}")
        print()
    
        # Restore for next simulation
        G.nodes[PRODUCT_NODE_ID]["price"] = original_price

        # Step 7: What-If Simulation 2 - Quantity increase
        print_header("Step 7: What-If Simulation - Quantity Increase")
        print("\n--- What-If: What if quantity increases from 2 to 10? ---")

        original_quantity = G.nodes[PRODUCT_NODE_ID]["quantity"]
        G.nodes[PRODUCT_NODE_ID]["quantity"] = 10

        print()
        execute_networkx_graph(G, dep_graph, verbose=False)

        print("New Computed Values:")
        for prop in OUTPUT_PROPERTIES:
            print(f"  - {prop.replace('_', ' ').title()}: {G.nodes[PRODUCT_NODE_ID].get(prop, 'N/A')}")
        print()

    except Exception as e:
        print(f"Error: {e}")
        print("\nTip: Please make sure Neo4j database is running")
        print("Start Neo4j: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/neo4j neo4j")


async def demo_with_real_neo4j():
    """Demo using real Neo4j database with ComputationExecutor"""
    print_header("Multi-Relation Computation Graph Demo")
    print(get_connection_info())

    try:
        data_provider = Neo4jDataProvider(uri=NEO4J_URI, user=NEO4J_USER, password=NEO4J_PASSWORD)
        print("Connecting to Neo4j...")
        print()

        graph, node_data_map = build_multi_relation_graph()

        # Step 1: Create Data Node
        print_header("Step 1: Create Data Node (Product)")
        data_node_id_map = {}
        for node_id, node_data in node_data_map.items():
            neo4j_id = await data_provider.create_node("Product", node_data)
            data_node_id_map[node_id] = neo4j_id
            print(f"  - Created: {node_data.get('name', node_id)} -> ID: {neo4j_id}")
        print(f"\nTotal: {len(data_node_id_map)} data nodes created")
        print()

        # Step 2: Create Computation Nodes
        print_header("Step 2: Create Computation Nodes")
        comp_node_id_map = {}
        for node_id, node in graph.computation_nodes.items():
            neo4j_id = await data_provider.create_node(
                "ComputationNode",
                {
                    "id": node.id,
                    "name": node.name,
                    "level": node.level.value,
                    "code": node.code,
                    "engine": node.engine.value,
                    "inputs_count": len(node.inputs),
                    "outputs_count": len(node.outputs),
                    "graph_id": graph.id,
                    "is_computation": True,
                }
            )
            comp_node_id_map[node_id] = neo4j_id
            print(f"  - Created: {node.name}")
            print(f"    Code: {node.code}")
        print(f"\nTotal: {len(comp_node_id_map)} computation nodes created")
        print()

        # Step 3: Create Relationships
        print_header("Step 3: Create Computation Relationships (Edges)")
        rel_count = 0
        for rel in graph.computation_relationships.values():
            source_id = (data_node_id_map.get(rel.source_id) if rel.relation_type == ComputationRelationType.DEPENDS_ON
                        else comp_node_id_map.get(rel.source_id))
            target_id = (comp_node_id_map.get(rel.target_id) if rel.relation_type == ComputationRelationType.DEPENDS_ON
                        else data_node_id_map.get(rel.target_id))

            if source_id and target_id:
                rel_props = {
                    "id": rel.id,
                    "name": rel.name,
                    "relation_type": rel.relation_type.value,
                    "level": rel.level,
                    "graph_id": graph.id,
                }
                if hasattr(rel, "datasource") and rel.datasource:
                    rel_props["datasource"] = f"{rel.datasource.entity_type}.{rel.datasource.property_name}"
                if hasattr(rel, "data_output") and rel.data_output:
                    rel_props["data_output"] = f"{rel.data_output.entity_type}.{rel.data_output.property_name}"

                await data_provider.create_relationship(source_id, target_id, rel.relation_type.value, rel_props)
                rel_count += 1
                print(f"  - Created: {rel.source_id} -> {rel.target_id} ({rel.relation_type.value})")
        print(f"\nTotal: {rel_count} relationships created")
        print()

        # Step 4: Query Graph
        print_header("Step 4: Query Graph Structure")
        driver = data_provider._get_driver()
        if driver:
            async with driver.session() as session:
                print("[Data Node]")
                query = "MATCH (n:Product) RETURN elementId(n) AS id, n ORDER BY n.name"
                result = await session.run(query)
                async for record in result:
                    print(f"  - {record.get('n.name', 'Unknown')}: ID {record['id']}")

                print("\n[Computation Nodes]")
                query = "MATCH (n:ComputationNode) RETURN elementId(n) AS id, n.name, n.code ORDER BY n.name"
                result = await session.run(query)
                async for record in result:
                    print(f"  - {record['n.name']}: {record['n.code']}")

                print("\n[Computation Relationships]")
                query = """
                    MATCH (source)-[r]->(target)
                    RETURN source.name AS s, target.name AS t, type(r) AS rt, r.name AS rn
                    ORDER BY s, t
                """
                result = await session.run(query)
                async for record in result:
                    print(f"  - {record['s']} -> {record['t']} ({record['rt']}): {record['rn']}")

        # Step 5: Execute
        print()
        print_header("Step 5: Execute Computations")
        product_neo4j_id = data_node_id_map.get(PRODUCT_NODE_ID)
        if product_neo4j_id:
            print(f"Executing computations for product node: {product_neo4j_id}")
            print()

            executor = ComputationExecutor(data_provider)
            results = await executor.execute_and_write_back(graph=graph, start_node_id=product_neo4j_id)

            print("Computation Results:")
            for node_id, outputs in results.items():
                node = graph.computation_nodes.get(node_id)
                name = node.name if node else node_id
                print(f"  - {name}: {outputs}")
            print()

            # Step 6: Verify
            print_header("Step 6: Query Updated Data from Neo4j")
            verified = await verify_node_data(driver, product_neo4j_id)
            if verified:
                print_product_summary(verified)

        await data_provider.close()
        print("\nNeo4j connection closed")

    except Exception as e:
        print(f"Error: {e}")
        print("\nTip: Please make sure Neo4j database is running")
        print("Start Neo4j: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/neo4j neo4j")


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main entry point with demo mode selection"""
    print("Choose demo mode:")
    print("  1 - Neo4j Demo (ComputationExecutor)")
    print("  2 - NetworkX Demo (with Neo4j integration)")
    print("  3 - Both")
    print()

    choice = "3"  # Default: run both demos

    if choice == "2":
        await demo_with_networkx()
    elif choice == "3":
        await demo_with_real_neo4j()
        print()
        await demo_with_networkx()
    else:
        await demo_with_real_neo4j()

    print()
    print_header("Demo completed!")
    print("\nGraph structure:")
    print("  Data Node: Product (iPhone 15 Pro)")
    print("\nComputation Nodes:")
    print("  - calc_total: price * quantity")
    print("  - calc_discount: total_output * (1 - discount_rate)")
    print("  - calc_tax: price_after_discount * (1 + tax_rate)")
    print("\nRelationships (DEPENDS_ON: Data Node -> Computation Node):")
    print("  - Product.price -> calc_total")
    print("  - Product.quantity -> calc_total")
    print("\nRelationships (OUTPUT_TO: Computation Node -> Data Node):")
    print("  - calc_total -> Product.total_output")
    print("  - calc_discount -> Product.price_after_discount")
    print("  - calc_tax -> Product.final_price")
    print("\nView graph in Neo4j Browser at: http://localhost:7474")


if __name__ == "__main__":
    asyncio.run(main())

# 是否写回数据库
# 自动生成计算图
# 图落盘