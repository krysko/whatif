"""
Multi-Relation Computation Graph Demo

Demonstrates ComputationNode connecting to different properties of the same data node
using multiple relationship types (DEPENDS_ON and OUTPUT_TO).
"""

import asyncio
import sys
from pathlib import Path

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


def build_multi_relation_graph() -> tuple[ComputationGraph, dict]:
    """Build a computation graph with multiple relationships to same data node

    Returns:
        (graph, node_data_map) - graph definition and initial node data
    """

    # === Input/Output Specifications ===

    # Product inputs
    price_input = InputSpec(
        source_type="property",
        entity_type="Product",
        property_name="price",
    )

    quantity_input = InputSpec(
        source_type="property",
        entity_type="Product",
        property_name="quantity",
    )

    discount_rate_input = InputSpec(
        source_type="property",
        entity_type="Product",
        property_name="discount_rate",
    )

    tax_rate_input = InputSpec(
        source_type="property",
        entity_type="Product",
        property_name="tax_rate",
    )

    # Product outputs
    total_output = OutputSpec(
        target_type="property",
        entity_type="Product",
        property_name="total_output",
    )

    price_after_discount_output = OutputSpec(
        target_type="property",
        entity_type="Product",
        property_name="price_after_discount",
    )

    final_price_output = OutputSpec(
        target_type="property",
        entity_type="Product",
        property_name="final_price",
    )

    # === Computation Nodes ===

    # calc_total: Calculate total price = price * quantity
    calc_total = ComputationNode(
        id="calc_total",
        name="calculate_total_price",
        level=ComputationLevel.PROPERTY,
        inputs=(price_input, quantity_input),
        outputs=(total_output,),
        code="price * quantity",
        engine=ComputationEngine.PYTHON,
    )

    # calc_discount: Calculate discounted price = total_output * (1 - discount_rate)
    calc_discount = ComputationNode(
        id="calc_discount",
        name="apply_discount",
        level=ComputationLevel.PROPERTY,
        inputs=(total_output, discount_rate_input),
        outputs=(price_after_discount_output,),
        code="total_output * (1 - discount_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # calc_tax: Calculate final price = price_after_discount * (1 + tax_rate)
    calc_tax = ComputationNode(
        id="calc_tax",
        name="calculate_final_price",
        level=ComputationLevel.PROPERTY,
        inputs=(price_after_discount_output, tax_rate_input),
        outputs=(final_price_output,),
        code="price_after_discount * (1 + tax_rate)",
        engine=ComputationEngine.PYTHON,
    )

    # === Computation Relationships ===

    # calc_total dependencies:
    # 1. product_001.price -> calc_total (DEPENDS_ON)
    rel_price_to_calc_total = ComputationRelationship(
        id="rel_price_to_calc_total",
        source_id="product_001",
        target_id="calc_total",
        name="price_depends",
        relation_type=ComputationRelationType.DEPENDS_ON,
        level="property",
        datasource=price_input,
    )

    # 2. product_001.quantity -> calc_total (DEPENDS_ON)
    rel_quantity_to_calc_total = ComputationRelationship(
        id="rel_quantity_to_calc_total",
        source_id="product_001",
        target_id="calc_total",
        name="quantity_depends",
        relation_type=ComputationRelationType.DEPENDS_ON,
        level="property",
        datasource=quantity_input,
    )

    # 3. calc_total -> product_001.total_output (OUTPUT_TO)
    rel_calc_total_to_total_output = ComputationRelationship(
        id="rel_calc_total_to_total_output",
        source_id="calc_total",
        target_id="product_001",
        name="total_output_result",
        relation_type=ComputationRelationType.OUTPUT_TO,
        level="property",
        data_output=total_output,
    )

    # calc_discount dependencies:
    # 1. product_001.total_output -> calc_discount (DEPENDS_ON)
    rel_total_output_to_calc_discount = ComputationRelationship(
        id="rel_total_output_to_calc_discount",
        source_id="product_001",
        target_id="calc_discount",
        name="total_output_depends",
        relation_type=ComputationRelationType.DEPENDS_ON,
        level="property",
        datasource=total_output,
    )

    # 2. product_001.discount_rate -> calc_discount (DEPENDS_ON)
    rel_discount_rate_to_calc_discount = ComputationRelationship(
        id="rel_discount_rate_to_calc_discount",
        source_id="product_001",
        target_id="calc_discount",
        name="discount_rate_depends",
        relation_type=ComputationRelationType.DEPENDS_ON,
        level="property",
        datasource=discount_rate_input,
    )

    # 3. calc_discount -> product_001.price_after_discount (OUTPUT_TO)
    rel_calc_discount_to_price_after_discount = ComputationRelationship(
        id="rel_calc_discount_to_price_after_discount",
        source_id="calc_discount",
        target_id="product_001",
        name="price_after_discount_result",
        relation_type=ComputationRelationType.OUTPUT_TO,
        level="property",
        data_output=price_after_discount_output,
    )

    # calc_tax dependencies:
    # 1. product_001.price_after_discount -> calc_tax (DEPENDS_ON)
    rel_price_after_discount_to_calc_tax = ComputationRelationship(
        id="rel_price_after_discount_to_calc_tax",
        source_id="product_001",
        target_id="calc_tax",
        name="price_after_discount_depends",
        relation_type=ComputationRelationType.DEPENDS_ON,
        level="property",
        datasource=price_after_discount_output,
    )

    # 2. product_001.tax_rate -> calc_tax (DEPENDS_ON)
    rel_tax_rate_to_calc_tax = ComputationRelationship(
        id="rel_tax_rate_to_calc_tax",
        source_id="product_001",
        target_id="calc_tax",
        name="tax_rate_depends",
        relation_type=ComputationRelationType.DEPENDS_ON,
        level="property",
        datasource=tax_rate_input,
    )

    # 3. calc_tax -> product_001.final_price (OUTPUT_TO)
    rel_calc_tax_to_final_price = ComputationRelationship(
        id="rel_calc_tax_to_final_price",
        source_id="calc_tax",
        target_id="product_001",
        name="final_price_result",
        relation_type=ComputationRelationType.OUTPUT_TO,
        level="property",
        data_output=final_price_output,
    )

    # === Build Graph ===

    graph = ComputationGraph(id="multi_relation_computation_graph")

    # Add computation nodes
    graph = graph.add_computation_node(calc_total)
    graph = graph.add_computation_node(calc_discount)
    graph = graph.add_computation_node(calc_tax)

    # Add computation relationships
    # calc_total dependencies
    graph = graph.add_computation_relationship(rel_price_to_calc_total)
    graph = graph.add_computation_relationship(rel_quantity_to_calc_total)
    graph = graph.add_computation_relationship(rel_calc_total_to_total_output)

    # calc_discount dependencies
    graph = graph.add_computation_relationship(rel_total_output_to_calc_discount)
    graph = graph.add_computation_relationship(rel_discount_rate_to_calc_discount)
    graph = graph.add_computation_relationship(rel_calc_discount_to_price_after_discount)

    # calc_tax dependencies
    graph = graph.add_computation_relationship(rel_price_after_discount_to_calc_tax)
    graph = graph.add_computation_relationship(rel_tax_rate_to_calc_tax)
    graph = graph.add_computation_relationship(rel_calc_tax_to_final_price)

    # === Initial Data ===

    node_data_map = {
        "product_001": {
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


async def demo_with_real_neo4j():
    """Demo using real Neo4j database"""
    print("=" * 80)
    print("Multi-Relation Computation Graph Demo")
    print("=" * 80)
    print()

    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "123456789"

    print(f"Neo4j connection config:")
    print(f"  URI: {NEO4J_URI}")
    print(f"  User: {NEO4J_USER}")
    print()

    try:
        data_provider = Neo4jDataProvider(
            uri=NEO4J_URI,
            user=NEO4J_USER,
            password=NEO4J_PASSWORD,
        )

        print("Connecting to Neo4j...")
        print()

        graph, node_data_map = build_multi_relation_graph()

        # Step 1: Create Data Node
        print("=" * 80)
        print("Step 1: Create Data Node (Product)")
        print("=" * 80)

        data_node_id_map = {}
        for node_id, node_data in node_data_map.items():
            node_type = "Product"
            node_name = node_data.get("name", node_id)
            neo4j_node_id = await data_provider.create_node(node_type, node_data)
            data_node_id_map[node_id] = neo4j_node_id
            print(f"  - Created: {node_name} -> ID: {neo4j_node_id}")

        print()
        print(f"Total: {len(data_node_id_map)} data nodes created")
        print()

        # Step 2: Create Computation Nodes
        print("=" * 80)
        print("Step 2: Create Computation Nodes")
        print("=" * 80)

        comp_node_id_map = {}
        for node_id, node in graph.computation_nodes.items():
            neo4j_node_id = await data_provider.create_node(
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
            comp_node_id_map[node_id] = neo4j_node_id
            print(f"  - Created: {node.name}")
            print(f"    Code: {node.code}")

        print()
        print(f"Total: {len(comp_node_id_map)} computation nodes created")
        print()

        # Step 3: Create Computation Relationships (Edges)
        print("=" * 80)
        print("Step 3: Create Computation Relationships (Edges)")
        print("=" * 80)

        rel_count = 0
        for rel_id, rel in graph.computation_relationships.items():
            if rel.relation_type == ComputationRelationType.DEPENDS_ON:
                source_node_id = data_node_id_map.get(rel.source_id)
                target_node_id = comp_node_id_map.get(rel.target_id)
            elif rel.relation_type == ComputationRelationType.OUTPUT_TO:
                source_node_id = comp_node_id_map.get(rel.source_id)
                target_node_id = data_node_id_map.get(rel.target_id)
            else:
                continue

            if source_node_id and target_node_id:
                rel_props = {
                    "id": rel.id,
                    "name": rel.name,
                    "relation_type": rel.relation_type.value,
                    "level": rel.level,
                    "graph_id": graph.id,
                }

                if hasattr(rel, "datasource") and rel.datasource is not None:
                    rel_props["datasource"] = f"{rel.datasource.entity_type}.{rel.datasource.property_name}"

                if hasattr(rel, "data_output") and rel.data_output is not None:
                    rel_props["data_output"] = f"{rel.data_output.entity_type}.{rel.data_output.property_name}"

                await data_provider.create_relationship(
                    source_node_id,
                    target_node_id,
                    rel.relation_type.value,
                    rel_props,
                )
                rel_count += 1
                print(f"  - Created: {rel.source_id} -> {rel.target_id} ({rel.relation_type.value})")

        print()
        print(f"Total: {rel_count} relationships created")
        print()

        # Step 4: Query and Display Graph Structure
        print("=" * 80)
        print("Step 4: Query Graph Structure")
        print("=" * 80)
        print()

        driver = data_provider._get_driver()
        if driver is not None:
            async with driver.session() as session:
                print("[Data Node]")
                query = "MATCH (n:Product) RETURN elementId(n) AS node_id, n.name, n.price, n.quantity, n.discount_rate, n.tax_rate, n.total_output, n.price_after_discount, n.final_price"
                result = await session.run(query)
                async for record in result:
                    print(f"  - {record['n.name']}")
                    print(f"    Price: {record.get('n.price', 'N/A')}")
                    print(f"    Quantity: {record.get('n.quantity', 'N/A')}")

                print()
                print("[Computation Nodes]")
                query = "MATCH (n:ComputationNode) RETURN elementId(n) AS node_id, n.name, n.code ORDER BY n.name"
                result = await session.run(query)
                async for record in result:
                    print(f"  - {record['n.name']}")
                    print(f"    Code: {record['n.code']}")

                print()
                print("[Computation Relationships]")
                query = """
                    MATCH (source)-[r]->(target)
                    RETURN elementId(r) AS rel_id,
                           type(r) AS rel_type,
                           source.name AS source_name,
                           target.name AS target_name,
                           r.name AS rel_name,
                           r.level
                    ORDER BY source_name, target_name
                """
                result = await session.run(query)
                async for record in result:
                    rel_type = record['rel_type']
                    source_name = record['source_name']
                    target_name = record['target_name']
                    rel_name = record['rel_name']
                    level = record['r.level']
                    print(f"  - [{level}] {source_name} -> {target_name}")
                    print(f"    Type: {rel_type}")
                    print(f"    Name: {rel_name}")

        # Step 5: Execute Computations
        print()
        print("=" * 80)
        print("Step 5: Execute Computations")
        print("=" * 80)
        print()

        # Get the actual Neo4j node ID for the product
        product_neo4j_id = data_node_id_map.get("product_001")
        if product_neo4j_id:
            print(f"Executing computations for product node: {product_neo4j_id}")
            print()

            # Create executor with the Neo4j data provider
            executor = ComputationExecutor(data_provider)

            # Execute the graph and write results back to Neo4j
            results = await executor.execute_and_write_back(
                graph=graph,
                start_node_id=product_neo4j_id,
            )

            print("Computation Results:")
            for node_id, outputs in results.items():
                node = graph.computation_nodes.get(node_id)
                node_name = node.name if node else node_id
                print(f"  - {node_name}: {outputs}")
            print()

            # Step 6: Query Updated Data
            print()
            print("=" * 80)
            print("Step 6: Query Updated Data from Neo4j")
            print("=" * 80)
            print()

            async with driver.session() as session:
                query = "MATCH (n:Product) WHERE elementId(n) = $node_id RETURN n"
                result = await session.run(query, node_id=product_neo4j_id)
                record = await result.single()

                if record:
                    node_data = dict(record["n"])
                    print(f"Product: {node_data.get('name', 'Unknown')}")
                    print()
                    print("Original Inputs:")
                    print(f"  - Price: {node_data.get('price', 'N/A')}")
                    print(f"  - Quantity: {node_data.get('quantity', 'N/A')}")
                    print(f"  - Discount Rate: {node_data.get('discount_rate', 'N/A')}")
                    print(f"  - Tax Rate: {node_data.get('tax_rate', 'N/A')}")
                    print()
                    print("Computed Outputs:")
                    print(f"  - Total Output: {node_data.get('total_output', 'N/A')}")
                    print(f"  - Price After Discount: {node_data.get('price_after_discount', 'N/A')}")
                    print(f"  - Final Price: {node_data.get('final_price', 'N/A')}")

        await data_provider.close()
        print()
        print("Neo4j connection closed")

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Tip: Please make sure Neo4j database is running")
        print("Start Neo4j:")
        print('  docker run -p 7474:7474 -p 7687:768687 -e NEO4J_AUTH=neo4j/neo4j neo4j')


async def main():
    await demo_with_real_neo4j()

    print()
    print("=" * 80)
    print("Demo completed!")
    print("=" * 80)
    print()
    print("Graph structure:")
    print("  Data Node: Product (iPhone 15 Pro)")
    print()
    print("Computation Nodes:")
    print("  - calc_total: price * quantity")
    print("  - calc_discount: total_output * (1 - discount_rate)")
    print("  - calc_tax: price_after_discount * (1 + tax_rate)")
    print()
    print("Relationships (DEPENDS_ON: Data Node -> Computation Node):")
    print("  - Product.price -> calc_total")
    print("  - Product.quantity -> calc_total")
    print()
    print("Relationships (OUTPUT_TO: Computation Node -> Data Node):")
    print("  - calc_total -> Product.total_output")
    print("  - calc_discount -> Product.price_after_discount")
    print("  - calc_tax -> Product.final_price")
    print()
    print("You can view the graph in Neo4j Browser at: http://localhost:7474")


if __name__ == "__main__":
    asyncio.run(main())
