"""
Supply Chain Delay Demo with Neo4j

Flow: Neo4j data + defined computation graph -> load by graph -> execute -> What-If.

Demonstrates how material delivery delay propagates through the computation graph:
  Shipment (actual_delivery_days) -> delay_days -> ProductionPlan (actual_start_days) -> Product (production_ready_days).

What-If: change actual_delivery_days (e.g. from 100 to 108) and observe impact on
actual_start_days and production_ready_days.
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

# Output properties per data node are derived from graph OUTPUT_TO relationships (see main)


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

def build_supply_chain_graph() -> Tuple[ComputationGraph, Dict]:
    """
    Build supply chain computation graph: delivery delay -> actual start -> production ready.

    Graph structure:
        [Shipment] --planned_delivery_days, actual_delivery_days--> [calc_delay_days] --delay_days--> [Shipment]
        [Shipment] --delay_days--> [calc_actual_start_days] <--planned_start_days-- [ProductionPlan]
        [calc_actual_start_days] --actual_start_days--> [ProductionPlan]
        [ProductionPlan] --actual_start_days, production_duration_days--> [calc_production_ready_days] --production_ready_days--> [Product]

    Returns:
        (graph, node_data_map) - graph definition and initial node data
    """
    # Input specifications
    planned_delivery_input = InputSpec("property", "Shipment", "planned_delivery_days")
    actual_delivery_input = InputSpec("property", "Shipment", "actual_delivery_days")
    delay_days_input = InputSpec("property", "Shipment", "delay_days")
    planned_start_input = InputSpec("property", "ProductionPlan", "planned_start_days")
    actual_start_input = InputSpec("property", "ProductionPlan", "actual_start_days")
    production_duration_input = InputSpec("property", "ProductionPlan", "production_duration_days")

    # Output specifications
    delay_days_output = OutputSpec("property", "Shipment", "delay_days")
    actual_start_output = OutputSpec("property", "ProductionPlan", "actual_start_days")
    production_ready_output = OutputSpec("property", "Product", "production_ready_days")

    # Computation nodes
    calc_delay_days = ComputationNode(
        id="calc_delay_days",
        name="calculate_delay_days",
        level=ComputationLevel.PROPERTY,
        inputs=(planned_delivery_input, actual_delivery_input),
        outputs=(delay_days_output,),
        code="actual_delivery_days - planned_delivery_days",
        engine=ComputationEngine.PYTHON,
    )

    calc_actual_start_days = ComputationNode(
        id="calc_actual_start_days",
        name="calculate_actual_start_days",
        level=ComputationLevel.PROPERTY,
        inputs=(planned_start_input, delay_days_input),
        outputs=(actual_start_output,),
        code="planned_start_days + delay_days",
        engine=ComputationEngine.PYTHON,
    )

    calc_production_ready_days = ComputationNode(
        id="calc_production_ready_days",
        name="calculate_production_ready_days",
        level=ComputationLevel.PROPERTY,
        inputs=(actual_start_input, production_duration_input),
        outputs=(production_ready_output,),
        code="actual_start_days + production_duration_days",
        engine=ComputationEngine.PYTHON,
    )

    # Build computation relationships
    relationships = [
        # Shipment -> calc_delay_days
        ComputationRelationship(
            "rel_planned_delivery_to_calc_delay", "shipment_001", "calc_delay_days",
            "planned_delivery_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=planned_delivery_input
        ),
        ComputationRelationship(
            "rel_actual_delivery_to_calc_delay", "shipment_001", "calc_delay_days",
            "actual_delivery_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=actual_delivery_input
        ),
        # calc_delay_days -> Shipment
        ComputationRelationship(
            "rel_calc_delay_to_shipment", "calc_delay_days", "shipment_001",
            "delay_days_result", ComputationRelationType.OUTPUT_TO, "property", data_output=delay_days_output
        ),
        # Shipment (delay_days), ProductionPlan (planned_start_days) -> calc_actual_start_days
        ComputationRelationship(
            "rel_delay_days_to_calc_actual_start", "shipment_001", "calc_actual_start_days",
            "delay_days_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=delay_days_input
        ),
        ComputationRelationship(
            "rel_planned_start_to_calc_actual_start", "production_plan_001", "calc_actual_start_days",
            "planned_start_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=planned_start_input
        ),
        # calc_actual_start_days -> ProductionPlan
        ComputationRelationship(
            "rel_calc_actual_start_to_plan", "calc_actual_start_days", "production_plan_001",
            "actual_start_days_result", ComputationRelationType.OUTPUT_TO, "property", data_output=actual_start_output
        ),
        # ProductionPlan -> calc_production_ready_days
        ComputationRelationship(
            "rel_actual_start_to_calc_ready", "production_plan_001", "calc_production_ready_days",
            "actual_start_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=actual_start_input
        ),
        ComputationRelationship(
            "rel_duration_to_calc_ready", "production_plan_001", "calc_production_ready_days",
            "production_duration_depends", ComputationRelationType.DEPENDS_ON, "property", datasource=production_duration_input
        ),
        # calc_production_ready_days -> Product
        ComputationRelationship(
            "rel_calc_ready_to_product", "calc_production_ready_days", "product_001",
            "production_ready_days_result", ComputationRelationType.OUTPUT_TO, "property", data_output=production_ready_output
        ),
    ]

    # Build graph
    graph = ComputationGraph(id="supply_chain_delay")
    graph = graph.add_computation_node(calc_delay_days)
    graph = graph.add_computation_node(calc_actual_start_days)
    graph = graph.add_computation_node(calc_production_ready_days)
    for rel in relationships:
        graph = graph.add_computation_relationship(rel)

    return graph


# ============================================================================
# Main Entry Point
# ============================================================================

async def main():
    """Main: Neo4j data + computation graph -> load -> execute -> What-If (delivery delay)."""
    print_header("Supply Chain Delay Demo with Neo4j")
    print("Flow: Material delivery delay -> actual start days -> production ready days")
    print()

    graph = build_supply_chain_graph()
    # Derive output properties per data node from OUTPUT_TO relationships (no hardcoding)
    output_properties_by_node = graph.get_output_properties_by_data_node()

    try:
        neo4j_manager = Neo4jGraphManager(NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD)
        await neo4j_manager.connect()
        print("Connected to Neo4j")
        print()

        # Step 1: Load from Neo4j by uuid (missing nodes will raise ValueError)
        print_header("Step 1: Load from Neo4j (by computation graph uuids)")
        node_data_map = await neo4j_manager.load_graph_data_from_neo4j(graph)
        print(f"Loaded {len(node_data_map)} data nodes:")
        for node_uuid in node_data_map:
            print(f"  - {node_uuid}")
        print()

        # Step 2: Create computation nodes in Neo4j
        print_header("Step 2: Create Computation Nodes in Neo4j")
        comp_node_id_map = await neo4j_manager.create_computation_nodes(graph)
        print(f"Created {len(comp_node_id_map)} computation nodes")
        print()

        # Step 3: Create relationships in Neo4j
        print_header("Step 3: Create Relationships in Neo4j")
        await neo4j_manager.create_relationships(graph)
        print(f"Created {len(graph.computation_relationships)} relationships")
        print()

        # Step 4: Query graph structure from Neo4j
        print_header("Step 4: Query Graph Structure from Neo4j")
        await neo4j_manager.print_graph_structure()
        print()

        # Step 5: Execute computations
        print_header("Step 5: Execute Computations")
        executor = ComputationGraphExecutor(graph, node_data_map)
        executor.execute(verbose=True)
        executor.print_node_data("Computed Results")
        print()

        # Step 6: Write computed outputs to Neo4j (all three data nodes)
        print_header("Step 6: Write Outputs to Neo4j")
        for node_uuid, props in output_properties_by_node.items():
            await neo4j_manager.write_output_properties(
                node_uuid, executor.get_node_data(node_uuid), output_properties=props
            )
        print("Outputs written to Neo4j (delay_days, actual_start_days, production_ready_days)")
        print()

        # Step 7: What-If - Delivery delay (using WhatIfSimulator with output_targets for multi-node write)
        print_header("Step 7: What-If Simulation - Material Delivery Delay")
        simulator = WhatIfSimulator(executor, neo4j_manager)
        result = await simulator.simulate_property_change(
            "shipment_001",
            "actual_delivery_days",
            110,  # 10 days late
            title="Material Delivery Delay",
        )
        plan_data = result.get("production_plan_001", {})
        prod_data = result.get("product_001", {})
        print("\nImpact summary:")
        print(f"  actual_start_days:     {plan_data.get('actual_start_days')} (was 102 in baseline)")
        print(f"  production_ready_days: {prod_data.get('production_ready_days')} (was 107 in baseline)")
        print()

        await neo4j_manager.disconnect()
        print("Neo4j connection closed")
        print()
        print_header("Demo Completed!")
        print("View graph in Neo4j Browser at: http://localhost:7474")

    except Exception as e:
        print(f"Error: {e}")
        print("\nTip: Please make sure Neo4j database is running")
        print("Start Neo4j: docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/123456789 neo4j")


if __name__ == "__main__":
    asyncio.run(main())
