"""
Peer discovery via pluggable rendezvous (file-backed DHT by default).

Two clusters on separate networks discover each other by writing/reading
suite metadata through a shared rendezvous store — no central coordinator.
Works with zero network (local directory) or any transport that implements
the same put/get/list contract.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from openharness.mesh.events import EventType, make_event
from openharness.mesh.identity import PeerIdentity


class PeerInfo(BaseModel):
    """Advertised peer metadata exchanged over the mesh."""

    peer_id: str
    cluster_id: str
    region: str = "local"
    endpoint: str = ""
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    suites: List[Dict[str, Any]] = Field(default_factory=list)
    latency_ms_estimate: float = 0.0
    last_seen: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def capability_fingerprint(self) -> str:
        """Stable fingerprint of advertised capabilities for matching."""
        keys = sorted(f"{k}={self.capabilities[k]}" for k in self.capabilities)
        return "|".join(keys)


class RendezvousStore:
    """File-backed key/value rendezvous (local DHT stand-in).

    Directory layout::
        <root>/peers/<peer_id>.json
        <root>/suites/<suite_id>.json
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.peers_dir = self.root / "peers"
        self.suites_dir = self.root / "suites"
        self.peers_dir.mkdir(parents=True, exist_ok=True)
        self.suites_dir.mkdir(parents=True, exist_ok=True)

    def put_peer(self, info: PeerInfo) -> str:
        """Publish or refresh a peer record."""
        path = self.peers_dir / f"{info.peer_id}.json"
        path.write_text(info.model_dump_json(indent=2), encoding="utf-8")
        return str(path)

    def get_peer(self, peer_id: str) -> Optional[PeerInfo]:
        path = self.peers_dir / f"{peer_id}.json"
        if not path.exists():
            return None
        return PeerInfo(**json.loads(path.read_text(encoding="utf-8")))

    def list_peers(self, max_age_sec: Optional[float] = None) -> List[PeerInfo]:
        """List known peers, optionally filtering by last_seen freshness."""
        now = time.time()
        peers: List[PeerInfo] = []
        for path in sorted(self.peers_dir.glob("*.json")):
            try:
                info = PeerInfo(**json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError, ValueError):
                continue
            if max_age_sec is not None and (now - info.last_seen) > max_age_sec:
                continue
            peers.append(info)
        return peers

    def put_suite(self, suite_id: str, metadata: Dict[str, Any]) -> str:
        path = self.suites_dir / f"{suite_id}.json"
        payload = {"suite_id": suite_id, **metadata, "updated_at": time.time()}
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return str(path)

    def get_suite(self, suite_id: str) -> Optional[Dict[str, Any]]:
        path = self.suites_dir / f"{suite_id}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_suites(self) -> List[Dict[str, Any]]:
        suites: List[Dict[str, Any]] = []
        for path in sorted(self.suites_dir.glob("*.json")):
            try:
                suites.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError):
                continue
        return suites


class PeerRegistry:
    """Local registry that announces this peer and discovers remote peers."""

    def __init__(self, identity: PeerIdentity, store: RendezvousStore):
        self.identity = identity
        self.store = store
        self._local_suites: List[Dict[str, Any]] = []
        self.event_log: List[Dict[str, Any]] = []

    def advertise_suite(self, suite_id: str, name: str = "", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Gossip suite metadata into the rendezvous store."""
        meta = {
            "name": name,
            "origin_peer_id": self.identity.peer_id,
            "cluster_id": self.identity.cluster_id,
            "region": self.identity.region,
            **(metadata or {}),
        }
        self.store.put_suite(suite_id, meta)
        record = {"suite_id": suite_id, "name": name, **(metadata or {})}
        self._local_suites.append(record)
        event = make_event(
            EventType.SUITE_ADVERTISE,
            self.identity,
            payload={"suite_id": suite_id, "name": name},
        )
        self.event_log.append(event.to_audit_record())
        self.announce()
        return meta

    def announce(self, endpoint: str = "", latency_ms_estimate: float = 0.0) -> PeerInfo:
        """Publish this peer's presence and suite list (signed announce event)."""
        info = PeerInfo(
            peer_id=self.identity.peer_id,
            cluster_id=self.identity.cluster_id,
            region=self.identity.region,
            endpoint=endpoint or f"mesh://{self.identity.cluster_id}/{self.identity.peer_id}",
            capabilities=dict(self.identity.capabilities),
            suites=list(self._local_suites),
            latency_ms_estimate=latency_ms_estimate,
            last_seen=time.time(),
        )
        self.store.put_peer(info)
        event = make_event(
            EventType.PEER_ANNOUNCE,
            self.identity,
            payload=info.model_dump(),
        )
        self.event_log.append(event.to_audit_record())
        return info

    def discover_peers(self, exclude_self: bool = True, max_age_sec: Optional[float] = 3600.0) -> List[PeerInfo]:
        """Discover peers via rendezvous without a central coordinator (AC-5)."""
        peers = self.store.list_peers(max_age_sec=max_age_sec)
        if exclude_self:
            peers = [p for p in peers if p.peer_id != self.identity.peer_id]
        return peers

    def discover_suites(self) -> List[Dict[str, Any]]:
        """Return all suite metadata currently in the DHT."""
        return self.store.list_suites()

    def find_peers_with_capabilities(self, required: Dict[str, Any]) -> List[PeerInfo]:
        """Return discovered peers whose capabilities satisfy ``required``."""
        matches: List[PeerInfo] = []
        for peer in self.discover_peers():
            caps = peer.capabilities
            ok = True
            for key, value in required.items():
                if caps.get(key) != value:
                    ok = False
                    break
            if ok:
                matches.append(peer)
        return matches
