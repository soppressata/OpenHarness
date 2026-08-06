"""
Signed event schema for the Test Mesh.

Everything is an event; all events are signed; all signing is auditable.
Schema is versioned for cross-release compatibility (Black Box AC-16).
"""
from __future__ import annotations

import enum
import time
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from openharness.mesh.identity import PeerIdentity, _canonical_json


SCHEMA_VERSION = "1.0.0"


class EventType(str, enum.Enum):
    """Canonical mesh event kinds."""

    PEER_ANNOUNCE = "peer.announce"
    SUITE_ADVERTISE = "suite.advertise"
    RUN_REQUEST = "run.request"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_MANIFEST = "run.manifest"
    QUARANTINE = "cortex.quarantine"
    PROMOTION = "cortex.promotion"
    BLACKBOX_CAPTURE = "blackbox.capture"
    TELEMETRY = "commons.telemetry"
    POLICY_DECISION = "policy.decision"
    HEARTBEAT = "peer.heartbeat"


class MeshEvent(BaseModel):
    """Versioned, signed mesh event envelope."""

    schema_version: str = SCHEMA_VERSION
    event_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    event_type: EventType
    peer_id: str
    cluster_id: str = ""
    timestamp: float = Field(default_factory=time.time)
    payload: Dict[str, Any] = Field(default_factory=dict)
    signature: str = ""
    previous_event_id: Optional[str] = None

    def unsigned_body(self) -> Dict[str, Any]:
        """Fields covered by the signature (excludes signature itself)."""
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else self.event_type,
            "peer_id": self.peer_id,
            "cluster_id": self.cluster_id,
            "timestamp": self.timestamp,
            "payload": self.payload,
            "previous_event_id": self.previous_event_id,
        }

    def to_audit_record(self) -> Dict[str, Any]:
        """Auditable view; never includes key material."""
        body = self.unsigned_body()
        body["signature"] = self.signature
        body["signature_present"] = bool(self.signature)
        return body


def sign_event(event: MeshEvent, identity: PeerIdentity) -> MeshEvent:
    """Sign an event in-place with the given peer identity and return it."""
    if event.peer_id and event.peer_id != identity.peer_id:
        raise ValueError("event.peer_id does not match signing identity")
    event.peer_id = identity.peer_id
    if not event.cluster_id:
        event.cluster_id = identity.cluster_id
    event.signature = identity.sign_payload(event.unsigned_body())
    return event


def verify_event(event: MeshEvent, identity: PeerIdentity) -> bool:
    """Verify event signature against a peer identity."""
    if event.peer_id != identity.peer_id:
        return False
    if not event.signature:
        return False
    return identity.verify_payload(event.unsigned_body(), event.signature)


def make_event(
    event_type: EventType,
    identity: PeerIdentity,
    payload: Optional[Dict[str, Any]] = None,
    previous_event_id: Optional[str] = None,
) -> MeshEvent:
    """Construct and sign a mesh event."""
    event = MeshEvent(
        event_type=event_type,
        peer_id=identity.peer_id,
        cluster_id=identity.cluster_id,
        payload=payload or {},
        previous_event_id=previous_event_id,
    )
    return sign_event(event, identity)


def event_digest(event: MeshEvent) -> str:
    """Stable content digest of a signed event (for chaining/audit)."""
    import hashlib

    return hashlib.sha256(_canonical_json(event.to_audit_record())).hexdigest()
