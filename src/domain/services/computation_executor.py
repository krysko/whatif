"""
Data provider for Neo4j: abstract interface and Neo4j implementation.
Used by Neo4jGraphManager for graph persistence and by demos for read/write.
"""

from abc import ABC, abstractmethod

from typing import Any, Dict, List, Mapping, Optional, Tuple


class DataProvider(ABC):
    """
    Abstract data provider interface

    Reads data from Neo4j
    """

    @abstractmethod
    async def get_node_data(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Read node data from data source

        Args:
            node_id: The ID of the node to retrieve

        Returns:
            Dictionary containing node data, or None if node doesn't exist
        """
        pass

    @abstractmethod
    async def set_node_properties(
        self,
        node_id: str,
        properties: Mapping[str, Any],
    ) -> bool:
        """
        Write node properties to data source

        Args:
            node_id: The ID of the node to update
            properties: Dictionary of properties to set

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def create_node(
        self,
        node_type: str,
        properties: Mapping[str, Any],
    ) -> Optional[str]:
        """
        Create a new node in the data source

        Args:
            node_type: The type/label of the node to create
            properties: Dictionary of initial properties for the node

        Returns:
            The ID of the created node, or None if creation failed
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close the connection to the data source"""
        pass


class Neo4jDataProvider(DataProvider):
    """
    Neo4j data provider

    Connects to a real Neo4j database and reads/writes data
    """

    def __init__(
        self,
        uri: Optional[str] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        mock_data: Optional[Dict[str, Dict[str, Any]]] = None,
    ):
        """
        Initialize the Neo4j data provider

        Args:
            uri: Neo4j connection URI (e.g., "bolt://localhost:7687")
            user: Neo4j username
            password: Neo4j password
            mock_data: Optional mock data for testing
        """
        self.uri = uri
        self.user = user
        self.password = password
        self._mock_data = mock_data or {}
        self._driver = None
        self._using_mock = mock_data is not None

    def _get_driver(self):
        """Get or initialize the Neo4j driver"""
        if self._driver is None and not self._using_mock:
            self._initialize_driver()
        return self._driver

    def _initialize_driver(self) -> None:
        """Initialize the Neo4j driver"""
        try:
            from neo4j import AsyncGraphDatabase

            if self.uri and self.user and self.password:
                self._driver = AsyncGraphDatabase.driver(
                    self.uri,
                    auth=(self.user, self.password),
                )
            else:
                raise ValueError(
                    "URI, user, and password must all be provided "
                    "when not using mock_data"
                )
        except ImportError:
            raise ImportError(
                "neo4j package is required when not using mock_data. "
                "Install it with: pip install neo4j"
            )

    async def get_node_data(self, node_id: str) -> Optional[Dict[str, Any]]:
        """
        Get node data from Neo4j or mock storage

        Args:
            node_id: The ID of the node to retrieve

        Returns:
            Dictionary containing node data, or None if node doesn't exist
        """
        if self._using_mock:
            return self.get_mock_node_data(node_id)

        driver = self._get_driver()
        if driver is None:
            return None

        # Query to get all properties of the node
        cypher_query = "MATCH (n) WHERE elementId(n) = $node_id RETURN n"

        async with driver.session() as session:
            result = await session.run(cypher_query, node_id=node_id)
            record = await result.single()

            if record is None:
                return None

            node = record["n"]
            return dict(node)

    async def get_data_node_by_uuid(
        self, uuid: str
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Find the business node (Order, Invoice, etc.) with uuid; excludes DataNode.
        Used to read attributes for the computation graph; data is then materialized into DataNodes separately.

        Returns:
            (neo4j_id, properties) or None if not found.
        """
        if self._using_mock:
            for node_id, data in self._mock_data.items():
                if isinstance(data, dict) and data.get("type") != "relationship":
                    if data.get("uuid") == uuid:
                        props = {k: v for k, v in data.items() if k != "type"}
                        return (node_id, props)
            return None

        driver = self._get_driver()
        if driver is None:
            return None

        # Read from business nodes (Order, Invoice, etc.) only; do not read from DataNode
        cypher_query = (
            "MATCH (n) WHERE n.uuid = $uuid AND NOT (n:DataNode) "
            "RETURN elementId(n) AS neo4j_id, properties(n) AS props"
        )
        async with driver.session() as session:
            result = await session.run(cypher_query, uuid=uuid)
            record = await result.single()
            if record is None:
                return None
            props = dict(record["props"]) if record["props"] else {}
            return props

    async def set_node_properties(
        self,
        node_id: str,
        properties: Mapping[str, Any],
        *,
        match_by_uuid: bool = False,
    ) -> bool:
        """
        Write node properties to Neo4j or mock storage.

        Args:
            node_id: The node identifier (elementId when match_by_uuid=False, uuid when match_by_uuid=True).
            properties: Dictionary of properties to set.
            match_by_uuid: If True, match DataNode by uuid (n.uuid = $node_id); else match by elementId(n).

        Returns:
            True if successful, False otherwise
        """
        if self._using_mock:
            return self.set_mock_node_properties(node_id, properties)

        driver = self._get_driver()
        if driver is None:
            return False

        set_parts = []
        params: Dict[str, Any] = {"node_id": node_id}
        for key, val in properties.items():
            param_key = f"val_{len(set_parts)}"
            set_parts.append(f"n.{key} = ${param_key}")
            params[param_key] = val

        if match_by_uuid:
            cypher_query = f"MATCH (n:DataNode {{uuid: $node_id}}) SET {', '.join(set_parts)}"
        else:
            cypher_query = f"MATCH (n) WHERE elementId(n) = $node_id SET {', '.join(set_parts)}"

        async with driver.session() as session:
            result = await session.run(cypher_query, **params)
            await result.consume()

        return True

    async def create_node(
        self,
        node_type: str,
        properties: Mapping[str, Any],
    ) -> Optional[str]:
        """
        Create a new node in Neo4j or mock storage

        Args:
            node_type: The type/label of the node to create
            properties: Dictionary of initial properties for the node

        Returns:
            The ID of the created node, or None if creation failed
        """
        if self._using_mock:
            return self.create_mock_node(node_type, properties)

        driver = self._get_driver()
        if driver is None:
            return None

        # Build property string with proper Cypher value formatting
        prop_parts = []

        for key, val in properties.items():
            if isinstance(val, str):
                # String values need single quotes in a Cypher literal
                prop_parts.append(f"`{key}`: '{val}'")
            elif isinstance(val, (int, float)):
                # Numbers don't need quotes
                prop_parts.append(f"`{key}`: {val}")
            elif isinstance(val, bool):
                # Booleans use true/false
                prop_parts.append(f"`{key}`: {str(val).lower()}")
            else:
                # Other types convert to string with quotes
                prop_parts.append(f"`{key}`: '{str(val)}'")

        props_str = ", ".join(prop_parts)

        # Build query
        cypher_query = f"CREATE (n:{node_type} {{{props_str}}}) RETURN elementId(n) AS node_id"

        async with driver.session() as session:
            result = await session.run(cypher_query)
            record = await result.single()

            if record is None:
                return None

            return str(record["node_id"])

    async def merge_data_node(
        self, uuid: str, properties: Mapping[str, Any]
    ) -> Optional[str]:
        """
        MERGE a DataNode in Neo4j by uuid and set its properties.
        Used to materialize data (from business nodes) into DataNodes that the computation graph connects to.

        Returns:
            uuid of the DataNode (same as input), for use as stable identifier; None on failure.
        """
        if self._using_mock:
            mock_id = f"datanode_{uuid}"
            if mock_id not in self._mock_data:
                self._mock_data[mock_id] = {"type": "DataNode", "uuid": uuid}
            self._mock_data[mock_id].update(dict(properties))
            self._mock_data[mock_id]["uuid"] = uuid
            return uuid

        driver = self._get_driver()
        if driver is None:
            return None

        props = dict(properties)
        if "uuid" not in props:
            props["uuid"] = uuid

        async with driver.session() as session:
            result = await session.run(
                "MERGE (n:DataNode {uuid: $uuid}) SET n = $props RETURN n.uuid AS u",
                uuid=uuid,
                props=props,
            )
            record = await result.single()
            if record is None:
                return None
            return str(record["u"])

    def get_mock_node_data(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get node data from mock storage"""
        return self._mock_data.get(node_id)

    def set_mock_node_properties(
        self,
        node_id: str,
        properties: Mapping[str, Any],
    ) -> bool:
        """Set node properties in mock storage"""
        if node_id not in self._mock_data:
            self._mock_data[node_id] = {}
        self._mock_data[node_id].update(properties)
        return True

    def create_mock_node(self, node_type: str, properties: Mapping[str, Any]) -> Optional[str]:
        """Create a new node in mock storage"""
        import uuid

        node_id = str(uuid.uuid4())
        self._mock_data[node_id] = {"type": node_type, **properties}
        return node_id

    @property
    def mock_data(self) -> Dict[str, Dict[str, Any]]:
        """Get mock data for testing"""
        return self._mock_data

    @mock_data.setter
    def mock_data(self, value: Dict[str, Dict[str, Any]]) -> None:
        """Set mock data"""
        self._mock_data = value

    async def create_relationship(
        self,
        source_node_id: str,
        target_node_id: str,
        rel_type: str,
        properties: Optional[Mapping[str, Any]] = None,
        *,
        source_match_by_uuid: bool = False,
        target_match_by_uuid: bool = False,
    ) -> Optional[str]:
        """
        Create a relationship between two nodes in Neo4j.

        Args:
            source_node_id: Source identifier (uuid when source_match_by_uuid=True, else elementId).
            target_node_id: Target identifier (uuid when target_match_by_uuid=True, else elementId).
            rel_type: The type/label of the relationship.
            properties: Optional dictionary of relationship properties.
            source_match_by_uuid: If True, match source with MATCH (source:DataNode {uuid: $source_id}).
            target_match_by_uuid: If True, match target with MATCH (target:DataNode {uuid: $target_id}).

        Returns:
            The ID of the created relationship, or None if creation failed.
        """
        if self._using_mock:
            import uuid as _uuid
            rel_id = str(_uuid.uuid4())
            self._mock_data[rel_id] = {
                "type": "relationship",
                "source_id": source_node_id,
                "target_id": target_node_id,
                "rel_type": rel_type,
                "properties": properties or {},
            }
            return rel_id

        driver = self._get_driver()
        if driver is None:
            return None

        if properties:
            prop_parts = []
            for key, val in properties.items():
                if isinstance(val, str):
                    prop_parts.append(f"`{key}`: '{val}'")
                elif isinstance(val, (int, float)):
                    prop_parts.append(f"`{key}`: {val}")
                elif isinstance(val, bool):
                    prop_parts.append(f"`{key}`: {str(val).lower()}")
                else:
                    prop_parts.append(f"`{key}`: '{str(val)}'")
            props_str = " {" + ", ".join(prop_parts) + "}"
        else:
            props_str = ""

        if source_match_by_uuid:
            source_match = "MATCH (source:DataNode {uuid: $source_id})"
        else:
            source_match = "MATCH (source) WHERE elementId(source) = $source_id"
        if target_match_by_uuid:
            target_match = "MATCH (target:DataNode {uuid: $target_id})"
        else:
            target_match = "MATCH (target) WHERE elementId(target) = $target_id"

        cypher_query = f"""
            {source_match}
            {target_match}
            CREATE (source)-[r:{rel_type}{props_str}]->(target)
            RETURN elementId(r) AS rel_id
        """

        async with driver.session() as session:
            result = await session.run(
                cypher_query,
                source_id=source_node_id,
                target_id=target_node_id,
            )
            record = await result.single()

            if record is None:
                return None

            return str(record["rel_id"])

    async def close(self) -> None:
        """Close the Neo4j driver"""
        if self._driver is not None:
            await self._driver.close()
            self._driver = None
