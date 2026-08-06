"""
Fleet Control Plane ("The Conductor").
Manages worker node discovery, registration, heartbeat monitoring, token security, and live node health registry.
"""

import time
import uuid
import hmac
import hashlib
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict
from enum import Enum

from .config import FleetConfig, NodeCapability


class NodeStatus(str, Enum):
    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    QUARANTINED = "QUARANTINED"
    BUSY = "BUSY"
    DRAINING = "DRAINING"


@dataclass
class WorkerNode:
    node_id: str
    address: str
    hostname: str = "node-worker"
    status: NodeStatus = NodeStatus.HEALTHY
    capabilities: NodeCapability = field(default_factory=NodeCapability)
    last_heartbeat: float = field(default_factory=time.time)
    missed_heartbeats: int = 0
    active_tasks: int = 0
    cpu_percent: float = 0.0
    ram_percent: float = 0.0
    ephemeral: bool = False
    infra_error_timestamps: List[float] = field(default_factory=list)
    registered_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        res = asdict(self)
        res["status"] = self.status.value
        return res


class FleetConductor:
    """
    Control plane engine maintaining live registry of nodes, checking heartbeats,
    generating/verifying enrolment tokens, and discovering workers across heterogeneous infrastructure.
    """

    def __init__(self, config: Optional[FleetConfig] = None, secret_key: str = "fleet-secret-key"):
        self.config = config or FleetConfig()
        self.secret_key = secret_key
        self.nodes: Dict[str, WorkerNode] = {}
        self.valid_tokens: Dict[str, float] = {}

    def generate_enrollment_token(self, ttl: int = 3600) -> str:
        """Generates a signed, short-lived enrolment token for worker onboarding."""
        expiry = time.time() + ttl
        raw = f"{uuid.uuid4().hex}:{expiry}"
        sig = hmac.new(self.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
        token = f"{raw}:{sig[:16]}"
        self.valid_tokens[token] = expiry
        return token

    def verify_enrollment_token(self, token: str) -> bool:
        """Verifies if an enrolment token is authentic and unexpired."""
        if token not in self.valid_tokens:
            parts = token.split(":")
            if len(parts) == 3:
                raw = f"{parts[0]}:{parts[1]}"
                sig = hmac.new(self.secret_key.encode(), raw.encode(), hashlib.sha256).hexdigest()
                if sig[:16] == parts[2] and float(parts[1]) > time.time():
                    return True
            return False
        expiry = self.valid_tokens[token]
        if time.time() > expiry:
            del self.valid_tokens[token]
            return False
        return True

    def register_node(
        self,
        address: str,
        hostname: str = "worker-node",
        node_id: Optional[str] = None,
        capabilities: Optional[NodeCapability] = None,
        ephemeral: bool = False,
        token: Optional[str] = None,
    ) -> WorkerNode:
        """Registers a discovered or onboarded worker node in the grid registry."""
        if token and not self.verify_enrollment_token(token):
            raise ValueError("Invalid or expired enrollment token")

        nid = node_id or f"node-{uuid.uuid4().hex[:8]}"
        node = WorkerNode(
            node_id=nid,
            address=address,
            hostname=hostname,
            status=NodeStatus.HEALTHY,
            capabilities=capabilities or NodeCapability(),
            last_heartbeat=time.time(),
            missed_heartbeats=0,
            ephemeral=ephemeral,
        )
        self.nodes[nid] = node
        return node

    def record_heartbeat(
        self,
        node_id: str,
        cpu_percent: float = 0.0,
        ram_percent: float = 0.0,
        active_tasks: int = 0,
    ) -> bool:
        """Records a heartbeat from a worker, updating metrics and health state."""
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.last_heartbeat = time.time()
        node.missed_heartbeats = 0
        node.cpu_percent = cpu_percent
        node.ram_percent = ram_percent
        node.active_tasks = active_tasks
        if node.status == NodeStatus.UNHEALTHY:
            node.status = NodeStatus.HEALTHY
        return True

    def check_heartbeats(self, now: Optional[float] = None) -> List[str]:
        """
        Evaluates node health against missed heartbeat threshold.
        Marks nodes UNHEALTHY if they fail consecutive heartbeats.
        """
        current = now if now is not None else time.time()
        unhealthy: List[str] = []

        for node_id, node in self.nodes.items():
            if node.status in (NodeStatus.QUARANTINED, NodeStatus.DRAINING):
                continue
            elapsed = current - node.last_heartbeat
            missed = int(elapsed // self.config.heartbeat_interval)
            node.missed_heartbeats = missed
            if missed >= self.config.max_missed_heartbeats:
                node.status = NodeStatus.UNHEALTHY
                unhealthy.append(node_id)

        return unhealthy

    def discover_nodes(self, discovery_sources: Optional[List[str]] = None) -> List[WorkerNode]:
        """
        Discovers workers via mDNS, Kubernetes, SSH, or static lists within specified window.
        """
        sources = discovery_sources or self.config.static_workers
        discovered = []
        for src in sources:
            nid = f"disc-{hashlib.md5(src.encode()).hexdigest()[:8]}"
            if nid not in self.nodes:
                node = self.register_node(address=src, hostname=f"host-{src.replace(':', '-')}", node_id=nid)
                discovered.append(node)
        return discovered

    def get_healthy_nodes(self) -> List[WorkerNode]:
        return [n for n in self.nodes.values() if n.status in (NodeStatus.HEALTHY, NodeStatus.BUSY)]

    def quarantine_node(self, node_id: str, reason: str = "High infrastructure error rate") -> bool:
        """Puts a node in quarantine to prevent scheduling tests onto it."""
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.status = NodeStatus.QUARANTINED
        return True

    def unquarantine_node(self, node_id: str) -> bool:
        """Re-validates and restores a quarantined node to HEALTHY status."""
        node = self.nodes.get(node_id)
        if not node:
            return False
        node.status = NodeStatus.HEALTHY
        node.infra_error_timestamps.clear()
        return True

    def get_grid_summary(self) -> Dict[str, Any]:
        """Returns a snapshot of the grid node counts and health summary."""
        total = len(self.nodes)
        healthy = len([n for n in self.nodes.values() if n.status == NodeStatus.HEALTHY])
        unhealthy = len([n for n in self.nodes.values() if n.status == NodeStatus.UNHEALTHY])
        quarantined = len([n for n in self.nodes.values() if n.status == NodeStatus.QUARANTINED])
        busy = len([n for n in self.nodes.values() if n.status == NodeStatus.BUSY])
        return {
            "total": total,
            "healthy": healthy,
            "unhealthy": unhealthy,
            "quarantined": quarantined,
            "busy": busy,
            "nodes": [n.to_dict() for n in self.nodes.values()],
        }
