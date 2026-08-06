"""
Peer identity, HMAC attestation, and provenance signing for the Test Mesh.

Uses stdlib HMAC-SHA256 (no external crypto deps). Each peer holds a secret
signing key; the public peer_id is a stable fingerprint of the key material.
Secrets are never included in manifests or logs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
import uuid
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field, PrivateAttr


def _canonical_json(payload: Any) -> bytes:
    """Deterministic JSON encoding for signing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def fingerprint_key(secret: bytes) -> str:
    """Derive a public peer fingerprint from secret key material."""
    return hashlib.sha256(secret).hexdigest()[:32]


class Attestation(BaseModel):
    """Signed provenance attestation for a mesh action."""

    peer_id: str
    action: str
    subject: str
    timestamp: float = Field(default_factory=time.time)
    nonce: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    signature: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def payload_for_signing(self) -> Dict[str, Any]:
        """Return the attestable fields excluding the signature itself."""
        return {
            "peer_id": self.peer_id,
            "action": self.action,
            "subject": self.subject,
            "timestamp": self.timestamp,
            "nonce": self.nonce,
            "metadata": self.metadata,
        }


class PeerIdentity(BaseModel):
    """mTLS-style peer identity backed by a local signing secret.

    The secret is never serialized by default. Export verification material
    (peer_id + secret) only over a trusted channel for third-party verify.
    """

    peer_id: str = ""
    cluster_id: str = Field(default_factory=lambda: f"cluster-{uuid.uuid4().hex[:8]}")
    region: str = "local"
    capabilities: Dict[str, Any] = Field(default_factory=dict)
    created_at: float = Field(default_factory=time.time)
    _secret: bytes = PrivateAttr(default=b"")

    def model_post_init(self, __context: Any) -> None:
        if not self._secret:
            object.__setattr__(self, "_secret", secrets.token_bytes(32))
        if not self.peer_id:
            object.__setattr__(self, "peer_id", fingerprint_key(self._secret))

    @classmethod
    def generate(
        cls,
        cluster_id: Optional[str] = None,
        region: str = "local",
        capabilities: Optional[Dict[str, Any]] = None,
        secret: Optional[bytes] = None,
    ) -> "PeerIdentity":
        """Create a new peer identity with fresh (or provided) key material."""
        sec = secret if secret is not None else secrets.token_bytes(32)
        identity = cls(
            peer_id=fingerprint_key(sec),
            cluster_id=cluster_id or f"cluster-{uuid.uuid4().hex[:8]}",
            region=region,
            capabilities=capabilities or {},
        )
        object.__setattr__(identity, "_secret", sec)
        return identity

    @classmethod
    def from_secret(
        cls,
        secret: bytes,
        cluster_id: Optional[str] = None,
        region: str = "local",
        capabilities: Optional[Dict[str, Any]] = None,
    ) -> "PeerIdentity":
        """Rehydrate an identity from known secret bytes (for verification peers)."""
        return cls.generate(
            cluster_id=cluster_id,
            region=region,
            capabilities=capabilities,
            secret=secret,
        )

    def export_public(self) -> Dict[str, Any]:
        """Public descriptor safe to gossip (never includes secret)."""
        return {
            "peer_id": self.peer_id,
            "cluster_id": self.cluster_id,
            "region": self.region,
            "capabilities": dict(self.capabilities),
            "created_at": self.created_at,
        }

    def export_verification_material(self) -> Dict[str, str]:
        """Export material needed by a third party to verify signatures.

        WARNING: contains secret key material. Never log or commit.
        """
        return {
            "peer_id": self.peer_id,
            "secret_hex": self._secret.hex(),
        }

    def sign_bytes(self, data: bytes) -> str:
        """HMAC-SHA256 sign raw bytes; return hex digest."""
        if not self._secret:
            raise ValueError("PeerIdentity has no signing secret")
        return hmac.new(self._secret, data, hashlib.sha256).hexdigest()

    def sign_payload(self, payload: Any) -> str:
        """Sign a JSON-serializable payload."""
        return self.sign_bytes(_canonical_json(payload))

    def verify_bytes(self, data: bytes, signature: str) -> bool:
        """Verify an HMAC signature against this peer's secret."""
        expected = self.sign_bytes(data)
        return hmac.compare_digest(expected, signature)

    def verify_payload(self, payload: Any, signature: str) -> bool:
        """Verify a signed JSON-serializable payload."""
        return self.verify_bytes(_canonical_json(payload), signature)

    def attest(self, action: str, subject: str, metadata: Optional[Dict[str, Any]] = None) -> Attestation:
        """Create a signed provenance attestation."""
        att = Attestation(
            peer_id=self.peer_id,
            action=action,
            subject=subject,
            metadata=metadata or {},
        )
        att.signature = self.sign_payload(att.payload_for_signing())
        return att

    def verify_attestation(self, attestation: Attestation) -> bool:
        """Verify an attestation was signed by this peer."""
        if attestation.peer_id != self.peer_id:
            return False
        return self.verify_payload(attestation.payload_for_signing(), attestation.signature)


def verify_with_material(material: Dict[str, str], payload: Any, signature: str) -> bool:
    """Third-party verification using exported verification material."""
    secret = bytes.fromhex(material["secret_hex"])
    peer = PeerIdentity.from_secret(secret)
    if material.get("peer_id") and peer.peer_id != material["peer_id"]:
        return False
    return peer.verify_payload(payload, signature)
