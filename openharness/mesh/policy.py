"""
Policy-as-code for the Test Mesh.

Defines per-project data residency, peer acceptance, and telemetry consent;
enforced at runtime before any cross-boundary action.
"""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field

from openharness.mesh.discovery import PeerInfo
from openharness.mesh.events import EventType, make_event
from openharness.mesh.identity import PeerIdentity


class MeshPolicy(BaseModel):
    """Declarative mesh policy for a project (AC-21)."""

    project_id: str = "default"
    telemetry_consent: bool = False
    allowed_regions: List[str] = Field(default_factory=lambda: ["*"])
    denied_regions: List[str] = Field(default_factory=list)
    allowed_peer_ids: List[str] = Field(default_factory=lambda: ["*"])
    denied_peer_ids: List[str] = Field(default_factory=list)
    allowed_cluster_ids: List[str] = Field(default_factory=lambda: ["*"])
    data_residency: str = "local"  # local | region | global
    allow_airgapped_export: bool = True
    allow_remote_execution: bool = True
    require_dual_signatures: bool = True
    max_peer_latency_ms: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def allows_region(self, region: str) -> bool:
        if region in self.denied_regions:
            return False
        if "*" in self.allowed_regions:
            return True
        return region in self.allowed_regions

    def allows_peer(self, peer_id: str, cluster_id: str = "", region: str = "local") -> bool:
        if peer_id in self.denied_peer_ids:
            return False
        if cluster_id and cluster_id not in self.allowed_cluster_ids and "*" not in self.allowed_cluster_ids:
            return False
        if not self.allows_region(region):
            return False
        if "*" in self.allowed_peer_ids:
            return True
        return peer_id in self.allowed_peer_ids


class PolicyDecision(BaseModel):
    """Runtime enforcement result."""

    allowed: bool
    action: str
    reason: str
    timestamp: float = Field(default_factory=time.time)
    policy_project_id: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)


class PolicyEngine:
    """Enforces MeshPolicy at runtime; emits auditable decision events."""

    def __init__(self, policy: MeshPolicy, identity: Optional[PeerIdentity] = None):
        self.policy = policy
        self.identity = identity
        self.decisions: List[PolicyDecision] = []

    def _record(self, allowed: bool, action: str, reason: str, details: Optional[Dict[str, Any]] = None) -> PolicyDecision:
        decision = PolicyDecision(
            allowed=allowed,
            action=action,
            reason=reason,
            policy_project_id=self.policy.project_id,
            details=details or {},
        )
        self.decisions.append(decision)
        if self.identity:
            make_event(
                EventType.POLICY_DECISION,
                self.identity,
                payload=decision.model_dump(),
            )
        return decision

    def check_telemetry(self) -> PolicyDecision:
        if not self.policy.telemetry_consent:
            return self._record(False, "telemetry", "telemetry_consent=false")
        return self._record(True, "telemetry", "consent_granted")

    def check_peer(self, peer: PeerInfo) -> PolicyDecision:
        if not self.policy.allow_remote_execution:
            return self._record(False, "peer_accept", "remote_execution_disabled", {"peer_id": peer.peer_id})
        if not self.policy.allows_peer(peer.peer_id, peer.cluster_id, peer.region):
            return self._record(
                False,
                "peer_accept",
                "peer_not_allowed_by_policy",
                {"peer_id": peer.peer_id, "region": peer.region, "cluster_id": peer.cluster_id},
            )
        if self.policy.max_peer_latency_ms is not None and peer.latency_ms_estimate > self.policy.max_peer_latency_ms:
            return self._record(
                False,
                "peer_accept",
                "peer_latency_exceeds_max",
                {"latency_ms": peer.latency_ms_estimate, "max": self.policy.max_peer_latency_ms},
            )
        if self.policy.data_residency == "local":
            # local residency: only peers in the literal "local" region (or matching allowed list)
            if peer.region != "local" and not (
                "*" in self.policy.allowed_regions or peer.region in self.policy.allowed_regions
            ):
                return self._record(
                    False,
                    "peer_accept",
                    "data_residency_local_violation",
                    {"peer_region": peer.region},
                )
        if self.policy.data_residency == "region":
            if not self.policy.allows_region(peer.region):
                return self._record(
                    False,
                    "peer_accept",
                    "data_residency_region_violation",
                    {"peer_region": peer.region},
                )
        return self._record(True, "peer_accept", "peer_accepted", {"peer_id": peer.peer_id})

    def check_airgapped_export(self) -> PolicyDecision:
        if not self.policy.allow_airgapped_export:
            return self._record(False, "airgapped_export", "airgapped_export_disabled")
        return self._record(True, "airgapped_export", "export_allowed")

    def filter_peers(self, peers: List[PeerInfo]) -> List[PeerInfo]:
        """Return only peers accepted by policy."""
        accepted: List[PeerInfo] = []
        for peer in peers:
            if self.check_peer(peer).allowed:
                accepted.append(peer)
        return accepted
