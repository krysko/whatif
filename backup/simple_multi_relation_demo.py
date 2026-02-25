"""
Simple Multi-Relation Demo

Demonstrates the basic structure of multiple relationship types
between data nodes and computation nodes.
"""

import asyncio

# Check if Neo4j is available
try:
    from neo4j import AsyncGraphDatabase

    NEO4J_AVAILABLE = True
except ImportError:
    NEO4J_AVAILABLE = False


async def demo_with_real_neo4j():
    """Demo using real Neo4j database"""
    print("=" * 80)
    print("Simple Multi-Relation Graph Demo")
    print("=" * 80)
    print()

    if not NEO4J_AVAILABLE:
        print("Neo4j driver not available!")
        print("Please install: pip install neo4j")
        return

    # Connection config
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "123456789"

    print(f"Neo4j connection config:")
    print(f"  URI: {NEO4J_URI}")
    print(f"  User: {NEO4J_USER}")
    print()

    try:
        driver = AsyncGraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

        print("Connecting to Neo4j...")
        print()

        # === Step 1: Create Data Node ===
        print("=" * 80)
        print("Step 1: Create Data Node (Product)")
        print("=" * 80)

        # Create product node with initial properties
        cypher = """
            CREATE (n:Product {
                name: 'iPhone 15 Pro',
                model: 'A3102',
                category: 'Smartphone',
                price: 100.0,
                quantity: 2,
                discount_rate: 0.1,
                tax_rate: 0.08,
                total_output: null,
                price_after_discount: null,
                final_price: null
            })
            RETURN elementId(n) AS node_id
        """

        async with driver.session() as session:
            result = await session.run(cypher)
            record = await result.single()
            product_node_id = record["node_id"]
            print(f"  - Created: Product (iPhone 15 Pro) -> ID: {product_node_id}")

        print()
        print(f"Total: 1 data node created")
        print()

        # === Step 2: Create Computation Nodes ===
        print("=" * 80)
        print("Step 2: Create Computation Nodes")
        print("=" * 80)

        # Create calc_total node
        cypher = """
            CREATE (n:ComputationNode {
                id: 'calc_total',
                name: 'calculate_total_price',
                level: 'property',
                code: 'price * quantity',
                engine: 'python',
                inputs_count: 2,
                outputs_count: 1,
                entity_type: 'Product',
                graph_id: 'multi_relation_graph',
                is_computation: true
            })
            RETURN elementId(n) AS node_id
        """

        async with driver.session() as session:
            result = await session.run(cypher)
            record = await result.single()
            calc_total_id = record["node_id"]
            print(f"  - Created: calc_total -> ID: {calc_total_id}")

        # Create calc_discount node
        cypher = """
            CREATE (n:ComputationNode {
                id: 'calc_discount',
                name: 'apply_discount',
                level: 'property',
                code: 'total_output * (1 - discount_rate)',
                engine: 'python',
                inputs_count: 2,
                outputs_count: 1,
                entity_type: 'Product',
                graph_id: 'multi_relation_graph',
                is_computation: true
            })
            RETURN elementId(n) AS node_id
        """

        async with driver.session() as session:
            result = await session.run(cypher)
            record = await result.single()
            calc_discount_id = record["node_id"]
            print(f"  - Created: calc_discount -> ID: {calc_discount_id}")

        # Create calc_tax node
        cypher = """
            CREATE (n:ComputationNode {
                id: 'calc_tax',
                name:calculate_final_price',
                level: 'property',
                code: 'price_after_discount * (1 + tax_rate)',
                engine: 'python',
                inputs_count: 2,
                outputs_count: 1,
                entity_type: 'Product',
                graph_id: 'multi_relation_graph',
                is_computation: true
            })
            RETURN elementId(n) AS node_id
        """

        async with driver.session() as session:
            result = await session.run(cypher)
            record = await result.single()
            calc_tax_id = record["node_id"]
            print(f"  - Created: calc_tax -> ID: {calc_tax_id}")

        comp_node_ids = {
            "calc_total": calc_total_id,
            "calc_discount": calc_discount_id,
            "calc_tax": calc_tax_id,
        }

        print()
        print(f"Total: {len(comp_node_ids)} computation nodes created")
        print()

        # === Step 3: Create Computation Relationships ===
        print("=" * 80)
        print("Step 3: Create Computation Relationships (Edges)")
        print("=" * 80)

        rel_count = 0

        # calc_total dependencies via DEPENDS_ON
        # 1. Product.price -> calc_total
        cypher = """
            MATCH (source:Product), (target:ComputationNode)
            WHERE elementId(target) = $target_id
            CREATE (source)-[r:DEPENDS_ON]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.datasource = 'Product.price'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "target_id": comp_node_ids["calc_total"],
            "rel_id": "rel_price_to_calc_total",
            "rel_name": "price_depends",
            "rel_type": "depends_on",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: Product -> calc_total (DEPENDS_ON)")

        # 2. Product.quantity -> calc_total (DEPENDS_ON)
        cypher = """
            MATCH (source:Product), (target:ComputationNode)
            WHERE elementId(target) = $target_id
            CREATE (source)-[r:DEPENDS_ON]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.datasource = 'Product.quantity'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "target_id": comp_node_ids["calc_total"],
            "rel_id": "rel_quantity_to_calc_total",
            "rel_name": "quantity_depends",
            "rel_type": "depends_on",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: Product -> calc_total (DEPENDS_ON)")

        # 3. calc_total -> Product.total_output (OUTPUT_TO)
        cypher = """
            MATCH (source:ComputationNode), (target:Product)
            WHERE elementId(source) = $source_id AND elementId(target) = $target_id
            CREATE (source)-[r:OUTPUT_TO]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.data_output = 'Product.total_output'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "source_id": comp_node_ids["calc_total"],
            "target_id": product_node_id,
            "rel_id": "rel_calc_total_to_total_output",
            "rel_name": "total_output_result",
            "rel_type": "output_to",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: calc_total -> Product.total_output (OUTPUT_TO)")

        # calc_discount dependencies
        # 1. Product.total_output -> calc_discount (DEPENDS_ON)
        cypher = """
            MATCH (source:Product), (target:ComputationNode)
            WHERE elementId(target) = $target_id
            CREATE (source)-[r:DEPENDS_ON]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.datasource = 'Product.total_output'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "target_id": comp_node_ids["calc_discount"],
            "rel_id": "rel_total_output_to_calc_discount",
            "rel_name": "total_output_depends",
            "rel_type": "depends_on",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: Product.total_output -> calc_discount (DEPENDS_ON)")

        # 2. Product.discount_rate -> calc_discount (DEPENDS_ON)
        cypher = """
            MATCH (source:Product), (target:ComputationNode)
            WHERE elementId(target) = $target_id
            CREATE (source)-[r:DEPENDS_ON]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.datasource = 'Product.discount_rate'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "target_id": comp_node_ids["calc_discount"],
            "rel_id": "rel_discount_rate_to_calc_discount",
            "rel_name": "discount_rate_depends",
            "rel_type": "depends_on",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: Product.discount_rate -> calc_discount (DEPENDS_ON)")

        # 3. calc_discount -> Product.price_after_discount (OUTPUT_TO)
        cypher = """
            MATCH (source:ComputationNode), (target:Product)
            WHERE elementId(source) = $source_id AND elementId(target) = $target_id
            CREATE (source)-[r:OUTPUT_TO]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.data_output = 'Product.price_after_discount'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "source_id": comp_node_ids["calc_discount"],
            "target_id": product_node_id,
            "rel_id": "rel_calc_discount_to_price_after_discount",
            "rel_name": "price_after_discount_result",
            "rel_type": "output_to",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: calc_discount -> Product.price_after_discount (OUTPUT_TO)")

        # calc_tax dependencies
        # 1. Product.price_after_discount -> calc_tax (DEPENDS_ON)
        cypher = """
            MATCH (source:Product), (target:ComputationNode)
            WHERE elementId(target) = $target_id
            CREATE (source)-[r:DEPENDS_ON]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.datasource = 'Product.price_after_discount'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "target_id": comp_node_ids["calc_tax"],
            "rel_id": "rel_price_after_discount_to_calc_tax",
            "rel_name": "price_after_discount_depends",
            "rel_type": "depends_on",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: Product.price_after_discount -> calc_tax (DEPENDS_ON)")

        # 2. Product.tax_rate -> calc_tax (DEPENDS_ON)
        cypher = """
            MATCH (source:Product), (target:ComputationNode)
            WHERE elementId(target) = $target_id
            CREATE (source)-[r:DEPENDS_ON]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.datasource = 'Product.tax_rate'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "target_id": comp_node_ids["calc_tax"],
            "rel_id": "rel_tax_rate_to_calc_tax",
            "rel_name": "tax_rate_depends",
            "rel_type": "depends_on",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: Product.tax_rate -> calc_tax (DEPENDS_ON)")

        # 3. calc_tax -> Product.final_price (OUTPUT_TO)
        cypher = """
            MATCH (source:ComputationNode), (target:Product)
            WHERE elementId(source) = $source_id AND elementId(target) = $target_id
            CREATE (source)-[r:OUTPUT_TO]->(target)
            SET r.id = $rel_id
            SET r.name = $rel_name
            SET r.relation_type = $rel_type
            SET r.level = $level
            SET r.data_output = 'Product.final_price'
            RETURN elementId(r) AS rel_id
        """
        params = {
            "source_id": comp_node_ids["calc_tax"],
            "target_id": product_node_id,
            "rel_id": "rel_calc_tax_to_final_price",
            "rel_name": "final_price_result",
            "rel_type": "output_to",
            "level": "property",
        }

        async with driver.session() as session:
            result = await session.run(cypher, params)
            rel_count += 1
            print(f"  - Created: calc_tax -> Product.final_price (OUTPUT_TO)")

        print()
        print(f"Total: {rel_count} relationships created")
        print()

        # === Step 4: Query and Display Graph Structure ===
        print("=" * 80)
        print("Step 4: Query Graph Structure")
        print("=" * 80)
        print()

        async with driver.session() as session:
            # Query data node
            print("[Data Node]")
            cypher = """
                MATCH (n:Product)
                RETURN elementId(n) AS node_id, n.name, n.model,
                       n.price, n.quantity, n.discount_rate, n.tax_rate,
                       n.total_output, n.price_after_discount, n.final_price
            """
            result = await session.run(cypher)
            async for record in result:
                print(f"  - {record['n.name']} [{record['n.model']}]")
                print(f"    Price: {record.get('n.price', 'N/A')}")
                print(f"    Quantity: {record.get('n.quantity', 'N/A')}")

            print()
            # Query computation nodes
            print("[Computation Nodes]")
            cypher = """
                MATCH (n:ComputationNode)
                RETURN elementId(n) AS node_id, n.name, n.code
                ORDER BY n.name
                """
            result = await session.run(cypher)
            async for record in result:
                print(f"  - {record['n.name']}")
                print(f"    Code: {record['n.code']}")

            print()
            # Query DEPENDS_ON relationships
            print("[DEPENDS_ON Relationships - Data -> Computation]")
            cypher = """
                MATCH (source:Product)-[r:DEPENDS_ON]->(target:ComputationNode)
                RETURN elementId(r) AS rel_id,
                       elementId(source) AS source_id,
                       source.name AS source_name,
                       elementId(target) AS target_id,
                       target.name AS target_name,
                       r.name AS rel_name,
                       r.relation_type AS rel_type,
                       r.datasource AS datasource,
                       r.level AS level
                ORDER BY target_name, rel_name
            """
            result = await session.run(cypher)
            async for record in result:
                print(f"  - [{level}] {record['source_name']} -> {record['target_name']}")
                print(f"    Type: {record['rel_type']}")
                print(f"    Datasource: {record.get('datasource', 'N/A')}")
                print(f"    Name: {record['rel_name']}")

            print()
            # Query OUTPUT_TO relationships
            print("[OUTPUT_TO Relationships - Computation -> Data]")
            cypher = """
                MATCH (source:ComputationNode)-[r:OUTPUT_TO]->(target:Product)
                RETURN elementId(r) AS rel_id,
                       elementId(source) AS source_id,
                       source.name AS source_name,
                       elementId(target) AS target_id,
                       target.name AS target_name,
                       r.name AS rel_name,
                       r.relation_type AS rel_type,
                       r.data_output AS data_output,
                       r.level AS level
                ORDER BY source_name, rel_name
            """
            result = await session.run(cypher)
            async for record in result:
                print(f"  - [{level}] {record['source_name']} -> {record['target_name']}")
                print(f"    Type: {record['rel_type']}")
                print(f"    DataOutput: {record.get('data_output', 'N/A')}")
                print(f"    Name: {record['rel_name']}")

        # Close connection
        await driver.close()
        print()
        print("Neo4j connection closed")

    except Exception as e:
        print(f"Error: {e}")
        print()
        print("Tip: Please make sure Neo4j database is running")
        print("Start Neo4j:")
        print('  docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/neo4j neo4j')


async def main():
    await demo_with_real_neo4j()

    print()
    print("=" * 80)
    print("Demo completed!")
    print("=" * 80)
    print()
    print("Graph structure explanation:")
    print()
    print("Data Node: Product (iPhone 15 Pro)")
    print()
    print("Computation Nodes:")
    print("    - calc_total: price * quantity")
    print("    - calc_discount: total_output * (1 - discount_rate)")
    print("    - calc_tax: price_after_discount * (1 + tax_rate)")
    print()
    print("Relationships (DEPENDS_ON - Data Node -> Computation Node):")
    print("    Product.price -> calc_total")
    print("    Product.quantity -> calc_total")
    print("    Product.total_output -> calc_discount")
    print("    Product.discount_rate -> calc_discount")
    print("    Product.price_after_discount -> calc_tax")
    print("    Product.tax_rate -> calc_tax")
    print()
    print("Relationships (OUTPUT_TO - Computation Node -> Data Node):")
    print("    calc_total -> Product.total_output")
    print("    calc_discount -> Product.price_after_discount")
    print("    calc_tax -> Product.final_price")
    print()
    print("You can view the graph in Neo4j Browser:")
    print("  http://localhost:7474")


if __name__ == "__main__":
    asyncio.run(main())
