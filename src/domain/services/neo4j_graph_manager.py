"""
Neo4j Graph Manager

Manages Neo4j graph operations for computation graphs.
"""

from typing import Dict, Iterable, List, Optional, Tuple

from ..models import (
    ComputationRelationType,
    ComputationGraph,
)
from .computation_executor import Neo4jDataProvider


# Default output properties for writing back to Neo4j
OUTPUT_PROPERTIES = ["subtotal", "tax"]


class Neo4jGraphManager:
    """Manages Neo4j graph operations for computation graphs"""

    def __init__(self, uri: str, user: str, password: str):
        self.uri = uri
        self.user = user
        self.password = password
        self.data_provider: Optional[Neo4jDataProvider] = None
        self.comp_node_id_map: Dict[str, str] = {}

    async def connect(self):
        """Connect to Neo4j"""
        self.data_provider = Neo4jDataProvider(
            uri=self.uri,
            user=self.user,
            password=self.password
        )

    async def disconnect(self):
        """Disconnect from Neo4j"""
        if self.data_provider:
            await self.data_provider.close()

    async def create_data_nodes(self, node_data_map: Dict[str, Dict]) -> Dict[str, str]:
        """Create nodes with label DataNode (legacy). Prefer create_business_nodes for scenario-specific labels."""
        data_node_id_map: Dict[str, str] = {}
        for node_id, node_data in node_data_map.items():
            props = dict(node_data)
            if "uuid" not in props:
                props["uuid"] = node_id
            neo4j_id = await self.data_provider.create_node("DataNode", props)
            data_node_id_map[node_id] = neo4j_id
        return data_node_id_map

    async def create_business_nodes(
        self, specs: Dict[str, Dict]
    ) -> Dict[str, str]:
        """
        Create scenario-specific nodes in Neo4j (e.g. Order, Invoice). Each must have "label".
        uuid is set automatically for later lookup when forming DataNodes for a computation graph.

        specs: uuid -> { "label": "Order", "order_id": "ORD-001", ... }

        Returns:
            Mapping of data node uuid to Neo4j node IDs
        """
        data_node_id_map: Dict[str, str] = {}
        for node_uuid, spec in specs.items():
            spec = dict(spec)
            label = spec.pop("label", None)
            if not label:
                raise ValueError(f"create_business_nodes: missing 'label' for uuid {node_uuid!r}")
            if "uuid" not in spec:
                spec["uuid"] = node_uuid
            neo4j_id = await self.data_provider.create_node(label, spec)
            data_node_id_map[node_uuid] = neo4j_id
        return data_node_id_map

    async def load_data_nodes_from_neo4j(
        self, uuids: Iterable[str]
    ) -> Tuple[Dict[str, Dict], Dict[str, str]]:
        """
        Per computation graph need: read properties from nodes (any label) by uuid,
        then materialize into DataNodes in Neo4j. Only these DataNodes are connected to ComputationNodes.

        Flow: find source node by uuid -> get properties -> MERGE DataNode with that data
        -> return node_data_map (for executor) and data_node_id_map (optional, e.g. for debug).
        """
        node_data_map: Dict[str, Dict] = {}
        for uuid in uuids:
            # Read from business node (Order, Invoice, etc.) by uuid
            result = await self.data_provider.get_data_node_by_uuid(uuid)
            if result is None:
                print(f"Warning: Node with uuid '{uuid}' not found in Neo4j, skipping.")
                continue
            props = result
            # Materialize into DataNode in Neo4j (MERGE by uuid); computation graph links to DataNode only
            data_node_uuid_id = await self.data_provider.merge_data_node(
                uuid, {**props, "uuid": uuid}
            )
            if data_node_uuid_id is None:
                continue
            node_data_map[uuid] = props
        return node_data_map

    async def load_graph_data_from_neo4j(
        self,
        graph: ComputationGraph,
    ) -> Dict[str, Dict]:
        """
        Load data nodes for a computation graph from Neo4j by uuid.
        Raises ValueError if any required data nodes are missing in Neo4j.

        Returns:
            node_data_map for use with ComputationGraphExecutor.
        """
        data_node_ids = graph.get_data_node_ids()
        node_data_map = await self.load_data_nodes_from_neo4j(data_node_ids)
        missing = set(data_node_ids) - set(node_data_map.keys())
        if missing:
            raise ValueError(
                f"Missing data nodes in Neo4j for graph: {sorted(missing)}. "
                "Create business nodes (e.g. via create_business_nodes or seed) before loading."
            )
        return node_data_map

    async def create_computation_nodes(self, graph: ComputationGraph) -> Dict[str, str]:
        """Create computation nodes in Neo4j

        Returns:
            Mapping of logical node IDs to Neo4j node IDs
        """
        self.comp_node_id_map = {}
        for node_id, node in graph.computation_nodes.items():
            node_props = {
                "id": node.id,
                "name": node.name,
                "level": node.level.value,
                "code": node.code,
                "engine": node.engine.value,
                "inputs_count": len(node.inputs),
                "outputs_count": len(node.outputs),
                "graph_id": graph.id,
                "is_computation": True,
                "priority": node.priority,
            }
            neo4j_id = await self.data_provider.create_node("ComputationNode", node_props)
            self.comp_node_id_map[node_id] = neo4j_id
        return self.comp_node_id_map

    async def create_relationships(self, graph: ComputationGraph):
        """Create relationships between nodes in Neo4j.
        DataNode endpoints use uuid (match_by_uuid); ComputationNode use elementId.
        """
        for rel in graph.computation_relationships.values():
            if rel.relation_type == ComputationRelationType.DEPENDS_ON:
                source_id = rel.source_id  # DataNode uuid
                target_id = self.comp_node_id_map.get(rel.target_id)
            else:
                source_id = self.comp_node_id_map.get(rel.source_id)
                target_id = rel.target_id  # DataNode uuid

            if source_id and target_id:
                rel_props = {
                    "uuid": rel.id,
                    "name": rel.name,
                    "relation_type": rel.relation_type.value,
                    "level": rel.level,
                    "graph_id": graph.id,
                }
                if hasattr(rel, "datasource") and rel.datasource:
                    rel_props["datasource"] = f"{rel.datasource.entity_type}.{rel.datasource.property_name}"
                if hasattr(rel, "data_output") and rel.data_output:
                    rel_props["data_output"] = f"{rel.data_output.entity_type}.{rel.data_output.property_name}"

                source_by_uuid = rel.relation_type == ComputationRelationType.DEPENDS_ON
                target_by_uuid = rel.relation_type == ComputationRelationType.OUTPUT_TO
                await self.data_provider.create_relationship(
                    source_id,
                    target_id,
                    rel.relation_type.value,
                    rel_props,
                    source_match_by_uuid=source_by_uuid,
                    target_match_by_uuid=target_by_uuid,
                )

    async def write_output_properties(self, node_uuid: str, node_data: Dict,
                                   output_properties: List[str] = None):
        """Write computed output properties to Neo4j (matches DataNode by uuid)."""
        if output_properties is None:
            output_properties = OUTPUT_PROPERTIES
        output_props = {prop: node_data.get(prop) for prop in output_properties}
        await self.data_provider.set_node_properties(
            node_uuid, output_props, match_by_uuid=True
        )

    async def print_graph_structure(self):
        """Query and print graph structure from Neo4j"""
        driver = self.data_provider._get_driver()
        if not driver:
            return

        async with driver.session() as session:
            print("\n[DataNodes (from business node attributes; linked to computation graph)]")
            query = "MATCH (n:DataNode) RETURN elementId(n) AS id, n ORDER BY n.uuid"
            result = await session.run(query)
            async for record in result:
                props = dict(record["n"])
                print(f"  - DataNode ID: {record['id']} uuid={props.get('uuid', '?')}")
                for key, value in props.items():
                    print(f"      {key}: {value}")

            print("\n[Computation Nodes]")
            query = "MATCH (n:ComputationNode) RETURN elementId(n) AS id, n.name, n.code ORDER BY n.name"
            result = await session.run(query)
            async for record in result:
                print(f"  - {record['n.name']} (ID: {record['id']}): {record['n.code']}")

            print("\n[Relationships]")
            query = """
                MATCH (source)-[r]->(target)
                RETURN type(r) AS rel_type, properties(r) AS rel_props,
                       labels(source)[0] AS source_type,
                       labels(target)[0] AS target_type
                ORDER BY rel_type
            """
            result = await session.run(query)
            async for record in result:
                props = record["rel_props"]
                source_info = f"{props.get('name', '')} ({record['source_type']})"
                target_info = f"{props.get('name', '')} ({record['target_type']})"
                print(f"  - {source_info} -> {target_info} [{record['rel_type']}]")
