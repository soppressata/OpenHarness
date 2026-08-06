"""
Signed run manifests and air-gapped suite bundles.

A remote run produces a manifest signed by both origin and executor,
verifiable by any third party holding both peers' verification material.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from openharness.mesh.identity import PeerIdentity, verify_with_material, _canonical_json


class SuiteResult(BaseModel):
    """Outcome of a single test within a suite run."""

    test_id: str
    status: str  # passed | failed | skipped | error
    duration_ms: float = 0.0
    message: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """Provenance-bearing record of a federated suite execution."""

    schema_version: str = "1.0.0"
    manifest_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    suite_id: str
    suite_name: str = ""
    origin_peer_id: str
    executor_peer_id: str = ""
    requested_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    results: List[SuiteResult] = Field(default_factory=list)
    binary_digest: str = ""
    environment: Dict[str, Any] = Field(default_factory=dict)
    origin_signature: str = ""
    executor_signature: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def body_for_origin(self) -> Dict[str, Any]:
        """Payload signed by the origin peer (request + suite identity)."""
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "origin_peer_id": self.origin_peer_id,
            "requested_at": self.requested_at,
            "binary_digest": self.binary_digest,
            "environment": self.environment,
            "metadata": self.metadata,
        }

    def body_for_executor(self) -> Dict[str, Any]:
        """Payload signed by the executor (includes results)."""
        return {
            **self.body_for_origin(),
            "executor_peer_id": self.executor_peer_id,
            "completed_at": self.completed_at,
            "results": [r.model_dump() for r in self.results],
            "origin_signature": self.origin_signature,
        }

    def content_digest(self) -> str:
        """Stable digest of the full dual-signed manifest."""
        payload = {
            **self.body_for_executor(),
            "executor_signature": self.executor_signature,
        }
        return hashlib.sha256(_canonical_json(payload)).hexdigest()


class AirGappedBundle(BaseModel):
    """Self-contained offline suite package for sneakernet / air-gapped exec."""

    schema_version: str = "1.0.0"
    bundle_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    suite_id: str
    suite_name: str = ""
    tests: List[Dict[str, Any]] = Field(default_factory=list)
    origin_peer_id: str
    origin_signature: str = ""
    packed_at: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def body_for_signing(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "suite_id": self.suite_id,
            "suite_name": self.suite_name,
            "tests": self.tests,
            "origin_peer_id": self.origin_peer_id,
            "packed_at": self.packed_at,
            "metadata": self.metadata,
        }


def create_run_manifest(
    suite_id: str,
    origin: PeerIdentity,
    suite_name: str = "",
    binary_digest: str = "",
    environment: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> RunManifest:
    """Create an origin-signed run request manifest."""
    manifest = RunManifest(
        suite_id=suite_id,
        suite_name=suite_name,
        origin_peer_id=origin.peer_id,
        binary_digest=binary_digest or hashlib.sha256(suite_id.encode()).hexdigest()[:16],
        environment=environment or {},
        metadata=metadata or {},
    )
    manifest.origin_signature = origin.sign_payload(manifest.body_for_origin())
    return manifest


def dual_sign_manifest(
    manifest: RunManifest,
    executor: PeerIdentity,
    results: List[SuiteResult],
) -> RunManifest:
    """Attach executor results and executor signature (AC-6)."""
    manifest.executor_peer_id = executor.peer_id
    manifest.completed_at = time.time()
    manifest.results = list(results)
    manifest.executor_signature = executor.sign_payload(manifest.body_for_executor())
    return manifest


def verify_manifest(
    manifest: RunManifest,
    origin_material: Dict[str, str],
    executor_material: Dict[str, str],
) -> Tuple[bool, List[str]]:
    """Verify both origin and executor signatures (third-party verifiable)."""
    errors: List[str] = []
    if not verify_with_material(origin_material, manifest.body_for_origin(), manifest.origin_signature):
        errors.append("origin_signature_invalid")
    if manifest.origin_peer_id != origin_material.get("peer_id"):
        errors.append("origin_peer_id_mismatch")
    if not manifest.executor_signature:
        errors.append("executor_signature_missing")
    elif not verify_with_material(executor_material, manifest.body_for_executor(), manifest.executor_signature):
        errors.append("executor_signature_invalid")
    if manifest.executor_peer_id and manifest.executor_peer_id != executor_material.get("peer_id"):
        errors.append("executor_peer_id_mismatch")
    return (len(errors) == 0, errors)


def pack_airgapped_bundle(
    suite_id: str,
    tests: List[Dict[str, Any]],
    origin: PeerIdentity,
    suite_name: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> AirGappedBundle:
    """Pack a full suite as a self-contained offline bundle (AC-7)."""
    bundle = AirGappedBundle(
        suite_id=suite_id,
        suite_name=suite_name,
        tests=tests,
        origin_peer_id=origin.peer_id,
        metadata=metadata or {},
    )
    bundle.origin_signature = origin.sign_payload(bundle.body_for_signing())
    return bundle


def execute_airgapped_bundle(
    bundle: AirGappedBundle,
    executor: PeerIdentity,
    runner: Optional[Callable[[Dict[str, Any]], SuiteResult]] = None,
    origin_material: Optional[Dict[str, str]] = None,
    origin: Optional[PeerIdentity] = None,
) -> RunManifest:
    """Execute an air-gapped bundle offline and return a dual-signed manifest.

    Default runner treats each test dict as a no-op pass unless ``expected_status``
    is set, or ``fail`` is True.

    If ``origin`` is provided (same key material that packed the bundle), the
    resulting manifest is dual-signed origin+executor. Otherwise the executor
    signs both roles so the offline result remains fully signed and auditable;
    the bundle origin signature remains the sneakernet provenance anchor.
    """
    if origin_material is not None:
        ok = verify_with_material(origin_material, bundle.body_for_signing(), bundle.origin_signature)
        if not ok:
            raise ValueError("air-gapped bundle origin signature invalid")
    elif origin is not None:
        if not origin.verify_payload(bundle.body_for_signing(), bundle.origin_signature):
            raise ValueError("air-gapped bundle origin signature invalid")

    def _default_runner(test: Dict[str, Any]) -> SuiteResult:
        test_id = str(test.get("id", test.get("name", "unknown")))
        if test.get("fail"):
            return SuiteResult(test_id=test_id, status="failed", message=str(test.get("message", "failed")))
        status = str(test.get("expected_status", "passed"))
        return SuiteResult(test_id=test_id, status=status, duration_ms=float(test.get("duration_ms", 0.0)))

    run = runner or _default_runner
    results = [run(t) for t in bundle.tests]

    origin_signer = origin if origin is not None else executor
    manifest = create_run_manifest(
        suite_id=bundle.suite_id,
        origin=origin_signer,
        suite_name=bundle.suite_name,
        metadata={
            "airgapped_bundle_id": bundle.bundle_id,
            "bundle_origin_peer_id": bundle.origin_peer_id,
            "bundle_origin_signature": bundle.origin_signature,
            **bundle.metadata,
        },
    )
    if origin is not None:
        manifest.origin_peer_id = origin.peer_id
    else:
        # Preserve bundle origin id in metadata; manifest origin is executor (offline).
        manifest.metadata["signed_origin_role"] = "executor_offline"
    return dual_sign_manifest(manifest, executor, results)


def write_manifest(path: str | Path, manifest: RunManifest) -> str:
    """Persist a manifest as JSON. Returns absolute path."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return str(p.resolve())


def read_manifest(path: str | Path) -> RunManifest:
    """Load a run manifest from disk."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunManifest(**data)


def write_bundle(path: str | Path, bundle: AirGappedBundle) -> str:
    """Persist an air-gapped bundle as JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(bundle.model_dump_json(indent=2), encoding="utf-8")
    return str(p.resolve())


def read_bundle(path: str | Path) -> AirGappedBundle:
    """Load an air-gapped bundle from disk."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return AirGappedBundle(**data)
