"""
Omniverse Deployment Graph module.
Provides graph-based representation of deployment desired states and orchestration logic.
"""
import uuid
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


class Node(BaseModel):
    """
    Represents a deployment entity or target state in the deployment graph.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    target_state: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list)
    status: str = "pending"  # pending, deploying, deployed, failed
    dependencies: List[str] = Field(default_factory=list)


class Edge(BaseModel):
    """
    Represents a relationship or dependency between two nodes in the graph.
    """
    source_node_id: str
    target_node_id: str
    relationship_type: str = "depends_on"
    properties: Dict[str, Any] = Field(default_factory=dict)


class DeploymentGraph(BaseModel):
    """
    The intelligent orchestration engine representing desired states and constraints.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    nodes: Dict[str, Node] = Field(default_factory=dict)
    edges: List[Edge] = Field(default_factory=list)

    def add_node(self, node: Node) -> None:
        """Add a deployment node to the graph."""
        self.nodes[node.id] = node

    def add_edge(self, source_id: str, target_id: str, relationship: str = "depends_on") -> None:
        """Add an edge defining a relationship between two nodes."""
        if source_id not in self.nodes or target_id not in self.nodes:
            raise ValueError("Both source and target nodes must exist in the graph.")
        edge = Edge(source_node_id=source_id, target_node_id=target_id, relationship_type=relationship)
        self.edges.append(edge)
        self.nodes[source_id].dependencies.append(target_id)

    def resolve_execution_order(self) -> List[List[Node]]:
        """
        Resolves the graph into execution tiers based on dependencies using topological sort.
        Returns a list of node tiers that can be deployed in parallel.
        """
        in_degree: Dict[str, int] = {node_id: 0 for node_id in self.nodes}
        graph_adj: Dict[str, List[str]] = {node_id: [] for node_id in self.nodes}

        for edge in self.edges:
            # target depends on source
            graph_adj[edge.target_node_id].append(edge.source_node_id)
            in_degree[edge.source_node_id] += 1

        queue: List[str] = [node_id for node_id, degree in in_degree.items() if degree == 0]
        execution_plan: List[List[Node]] = []

        while queue:
            tier_nodes = queue[:]
            queue.clear()
            execution_plan.append([self.nodes[node_id] for node_id in tier_nodes])
            
            for node_id in tier_nodes:
                for neighbor in graph_adj[node_id]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if sum(len(tier) for tier in execution_plan) != len(self.nodes):
            raise ValueError("Graph contains cyclic dependencies and cannot be resolved.")

        return execution_plan
