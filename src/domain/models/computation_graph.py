from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Set, Tuple

from .computation_node import ComputationNode
from .computation_relationship import ComputationRelationship
from .computation_relation_type import ComputationRelationType


@dataclass(frozen=True, slots=True)
class ComputationGraph:
    """Represents a computation graph with computation nodes and relationships"""
    id: str
    computation_nodes: Mapping[str, ComputationNode] = field(default_factory=dict)
    computation_relationships: Mapping[str, ComputationRelationship] = field(default_factory=dict)
    outgoing: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    incoming: Mapping[str, Tuple[str, ...]] = field(default_factory=dict)
    base_graph_id: str | None = None  # Reference to business data graph

    def get_computation_node(self, node_id: str) -> ComputationNode | None:
        """Get a computation node by ID"""
        return self.computation_nodes.get(node_id)

    def get_computation_relationship(self, relationship_id: str) -> ComputationRelationship | None:
        """Get a computation relationship by ID"""
        return self.computation_relationships.get(relationship_id)

    def get_outgoing_relationships(self, node_id: str) -> Tuple[ComputationRelationship, ...]:
        """Get all outgoing relationships from a node"""
        rel_ids = self.outgoing.get(node_id, ())
        return tuple(self.computation_relationships[rid] for rid in rel_ids if rid in self.computation_relationships)

    def get_incoming_relationships(self, node_id: str) -> Tuple[ComputationRelationship, ...]:
        """Get all incoming relationships to a node"""
        rel_ids = self.incoming.get(node_id, ())
        return tuple(self.computation_relationships[rid] for rid in rel_ids if rid in self.computation_relationships)

    def get_dependencies(self, node_id: str) -> Tuple[ComputationNode, ...]:
        """Get all a computation nodes that this node depends on"""
        incoming_rels = self.get_incoming_relationships(node_id)
        source_ids = tuple(rel.source_id for rel in incoming_rels if rel.relation_type.value == "depends_on")
        return tuple(self.computation_nodes[nid] for nid in source_ids if nid in self.computation_nodes)

    def get_dependents(self, node_id: str) -> Tuple[ComputationNode, ...]:
        """Get all computation nodes that depend on this node"""
        outgoing_rels = self.get_outgoing_relationships(node_id)
        target_ids = tuple(rel.target_id for rel in outgoing_rels if rel.relation_type.value == "output_to")
        return tuple(self.computation_nodes[nid] for nid in target_ids if nid in self.computation_nodes)

    def get_data_node_ids(self) -> Set[str]:
        """Collect uuid of data nodes referenced by this computation graph.
        Data nodes are DEPENDS_ON sources and OUTPUT_TO targets, excluding computation node IDs.
        """
        candidate_ids: Set[str] = set()
        for rel in self.computation_relationships.values():
            if rel.relation_type.value == "depends_on":
                candidate_ids.add(rel.source_id)
            elif rel.relation_type.value == "output_to":
                candidate_ids.add(rel.target_id)
        return candidate_ids - set(self.computation_nodes.keys())

    def get_output_properties_by_data_node(self) -> Dict[str, List[str]]:
        """Derive output property names per data node from OUTPUT_TO relationships.
        Only relationships whose target_id is a data node (not a computation node) are considered.
        Returns dict mapping data node id -> list of property names to write back.
        """
        comp_ids = set(self.computation_nodes.keys())
        out: Dict[str, List[str]] = {}
        for rel in self.computation_relationships.values():
            if rel.relation_type != ComputationRelationType.OUTPUT_TO:
                continue
            if rel.target_id in comp_ids:
                continue
            if not rel.data_output or not rel.data_output.property_name:
                continue
            if rel.target_id not in out:
                out[rel.target_id] = []
            out[rel.target_id].append(rel.data_output.property_name)
        return out

    def add_computation_node(self, node: ComputationNode) -> 'ComputationGraph':
        """Add a computation node and return a new ComputationGraph"""
        new_nodes = {**self.computation_nodes, node.id: node}
        return ComputationGraph(
            id=self.id,
            computation_nodes=new_nodes,
            computation_relationships=self.computation_relationships,
            outgoing=self.outgoing,
            incoming=self.incoming,
            base_graph_id=self.base_graph_id
        )

    def add_computation_relationship(self, relationship: ComputationRelationship) -> 'ComputationGraph':
        """Add a computation relationship and return a new ComputationGraph"""
        new_relationships = {**self.computation_relationships, relationship.id: relationship}

        # Update outgoing
        new_outgoing = dict(self.outgoing)
        if relationship.source_id in new_outgoing:
            new_outgoing[relationship.source_id] = (*new_outgoing[relationship.source_id], relationship.id)
        else:
            new_outgoing[relationship.source_id] = (relationship.id,)

        # Update incoming
        new_incoming = dict(self.incoming)
        if relationship.target_id in new_incoming:
            new_incoming[relationship.target_id] = (*new_incoming[relationship.target_id], relationship.id)
        else:
            new_incoming[relationship.target_id] = (relationship.id,)

        return ComputationGraph(
            id=self.id,
            computation_nodes=self.computation_nodes,
            computation_relationships=new_relationships,
            outgoing=new_outgoing,
            incoming=new_incoming,
            base_graph_id=self.base_graph_id
        )
