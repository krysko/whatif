"""
Simple Computation Chain Demo with Neo4j (Refactored)

Flow: Neo4j has data + defined computation graph -> load data from Neo4j by graph -> execute -> What-If.

- Data nodes in Neo4j are identified by uuid (e.g. order_001, invoice_001).
- Computation graph (nodes and relationships) is defined in code.
- Data is loaded from Neo4j according to the graph's data node uuids, then computations run and What-If can be performed.
- Optional: if DataNodes are missing in Neo4j, they are created from seed data (with uuid) then data is loaded again.
"""

import asyncio
import sys
from pathlib import Path
from typing import Tuple, Dict

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

# Import refactored classes from src
from domain.services import (
    ComputationGraphExecutor,
    Neo4jGraphManager,
    WhatIfSimulator,
)


# ============================================================================
# Configuration
# ============================================================================

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "123456789"
OUTPUT_PROPERTIES = ["subtotal", "tax"]


# ============================================================================
# Display Utilities
# ============================================================================

def print_header(title: str, width: int = 60):
    """Print section header"""
    print("=" * width)
    print(title)
    print("=" * width)
    print()


# ============================================================================
# Graph Construction
# ============================================================================

def build_computation_graph() -> Tuple[ComputationGraph, Dict]:
    """
    Build a simple computation graph with multiple data nodes and computation nodes.

    Graph structure:
        [Order] --price--> [Calc Subtotal] --subtotal--> [Invoice]
                      --quantity-->               --tax_rate-->
                                                [Calc Taxation] --tax--> [Invoice]
                                                             --subtotal-->

    Returns:
        (graph, node_data_map) - graph definition and initial node data
    """
    # Input specifications
    price_input = InputSpec("property", "Order", "price")
    quantity_input = InputSpec("property", "Order", "quantity")
    tax_rate_input = InputSpec("property", "Invoice", "tax_rate")
    subtotal_input = InputSpec("property", "Invoice", "subtotal")

    # Output specifications
    subtotal_output = OutputSpec("property", "Invoice", "subtotal")
    tax_output = OutputSpec("property", "Invoice", "tax")

    # Computation nodes
    calc_subtotal = ComputationNode(
        id="calc_subtotal",
        name="calculate_subtotal",
        level=ComputationLevel.PROPERTY,
        inputs=(price_input, quantity_input),
        outputs=(subtotal_output,),
        code="price * quantity",
        engine=ComputationEngine.PYTHON,
    )

    calc_tax = ComputationNode(
        id="calc_tax",
        name="calculate_tax",
        level=ComputationLevel.PROPERTY,
        inputs=(subtotal_input, tax_rate_input),
        outputs=(tax_output,),
        code="subtotal * tax_rate",
        engine=ComputationEngine.PYTHON,
    )

    # Build computation relationships
    relationships = [
        # Order -> calc_subtotal dependencies
        ComputationRelationship("rel_price_to_calc_subtotal", "order_001", "calc_subtotal",
            "price_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=price_input),
        ComputationRelationship("rel_quantity_to_calc_subtotal", "order_001", "calc_subtotal",
            "quantity_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=quantity_input),
        # calc_subtotal -> Invoice output
        ComputationRelationship("rel_calc_subtotal_to_invoice", "calc_subtotal", "invoice_001",
            "subtotal_result", ComputationRelationType.OUTPUT_TO, "property", data_output=subtotal_output),
        # Invoice -> calc_tax dependencies
        ComputationRelationship("rel_subtotal_to_calc_tax", "invoice_001", "calc_tax",
            "subtotal_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=subtotal_input),
        ComputationRelationship("rel_tax_rate_to_calc_tax", "invoice_001", "calc_tax",
            "tax_rate_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=tax_rate_input),
        # calc_tax -> Invoice output
        ComputationRelationship("rel_calc_tax_to_invoice", "calc_tax", "invoice_001",
            "tax_result", ComputationRelationType.OUTPUT_TO, "property", data_output=tax_output),
    ]

    # Build graph
    graph = ComputationGraph(id="simple_computation_chain")
    graph = graph.add_computation_node(calc_subtotal)
    graph = graph.add_computation_node(calc_tax)
    for rel in relationships:
        graph = graph.add_computation_relationship(rel)

    # Initial data for multiple data nodes
    node_data_map = {
        "order_001": {
            "order_id": "ORD-001",
            "customer": "Acme Corp",
            "price": 100.0,
            "quantity": 5,
        },
        "invoice_001": {
            "invoice_id": "INV-001",
            "customer": "Acme Corp",
            "tax_rate": 0.1,  # 10% tax
        },
    }

    return graph, node_data_map


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main: Neo4j data + computation graph -> load data from Neo4j -> execute -> What-If."""
    print_header("Simple Computation Chain Demo with Neo4j (Refactored)")
    print("Flow: Neo4j data + defined computation graph -> load data by graph -> execute -> What-If")
    print()

    # Build graph definition (and seed data for optional first-time create)
    graph, seed_node_data = build_computation_graph()

    try:
        neo4j_manager = Neo4jGraphManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        await neo4j_manager.connect()
        print("Connected to Neo4j")
        print()

        # Step 1: 同步数据节点、计算节点、计算关系到 Neo4j（一步完成）
        print_header("Step 1: Sync Graph to Neo4j (data nodes + computation nodes + relationships)")
        node_data_map = await neo4j_manager.sync_graph_to_neo4j(graph)
        print(f"Synced: {len(node_data_map)} data nodes, {len(graph.computation_nodes)} computation nodes, {len(graph.computation_relationships)} relationships")
        print()

        # Step 2: Query graph structure from Neo4j
        print_header("Step 2: Query Graph Structure from Neo4j")
        await neo4j_manager.print_graph_structure()
        print()

        # Step 3: Execute computations using loaded node_data_map
        print_header("Step 3: Execute Computations")
        executor = ComputationGraphExecutor(graph, node_data_map)
        executor.execute(verbose=True)
        executor.print_node_data("Computed Results")
        print()

        # Step 4: Write computed outputs to Neo4j
        print_header("Step 4: Write Outputs to Neo4j")
        await neo4j_manager.write_output_properties("invoice_001", executor.get_node_data("invoice_001"))
        print("Outputs written to Neo4j")
        print()

        # Step 5 & 6: What-If simulations (generic property change)
        print_header("Step 5: What-If Simulation - Price Increase")
        simulator = WhatIfSimulator(executor, neo4j_manager)
        await simulator.simulate_property_change(
            "order_001", "price", 150.0, title="Price Increase"
        )
        print()

        print_header("Step 6: What-If Simulation - Quantity Change")
        await simulator.simulate_property_change(
            "order_001", "quantity", 10, title="Quantity Change"
        )
        print()

        await neo4j_manager.disconnect()
        print("Neo4j connection closed")
        print()
        print_header("Demo Completed!")
        print("\nView graph in Neo4j Browser at: http://localhost:7474")

    except Exception as e:
        print(f"Error: {e}")
        print("\nTip: Please make sure Neo4j database is running")
        print("Start Neo4j: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/123456789 neo4j")


if __name__ == "__main__":
    asyncio.run(main())
