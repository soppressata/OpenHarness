"""
OpenHarness Test Mesh — federated execution, self-healing, black-box replay,
and global intelligence fabric.

Additive subsystem: existing OpenHarness APIs are unchanged. Nothing leaves a
cluster without an explicit per-project policy (default-private).
"""
from openharness.mesh.identity import PeerIdentity, Attestation
from openharness.mesh.events import MeshEvent, EventType, sign_event, verify_event, make_event
from openharness.mesh.manifest import (
    RunManifest,
    AirGappedBundle,
    SuiteResult,
    create_run_manifest,
    dual_sign_manifest,
    verify_manifest,
    pack_airgapped_bundle,
    execute_airgapped_bundle,
)
from openharness.mesh.discovery import PeerRegistry, PeerInfo, RendezvousStore
from openharness.mesh.scheduler import MeshScheduler, select_geo_optimal_peer
from openharness.mesh.cortex import CortexEngine, QuarantineDecision, TestRunOutcome
from openharness.mesh.blackbox import BlackBoxRecorder, BlackBoxRecording, replay_recording, delta_diff
from openharness.mesh.commons import (
    CommonsClient,
    TestGenomeRecipe,
    anonymize_telemetry,
    scrub_pii,
)
from openharness.mesh.policy import MeshPolicy, PolicyEngine
from openharness.mesh.mesh import TestMesh

__all__ = [
    "PeerIdentity",
    "Attestation",
    "MeshEvent",
    "EventType",
    "sign_event",
    "verify_event",
    "make_event",
    "SuiteResult",
    "RunManifest",
    "AirGappedBundle",
    "create_run_manifest",
    "dual_sign_manifest",
    "verify_manifest",
    "pack_airgapped_bundle",
    "execute_airgapped_bundle",
    "PeerRegistry",
    "PeerInfo",
    "RendezvousStore",
    "MeshScheduler",
    "select_geo_optimal_peer",
    "CortexEngine",
    "QuarantineDecision",
    "TestRunOutcome",
    "BlackBoxRecorder",
    "BlackBoxRecording",
    "replay_recording",
    "delta_diff",
    "CommonsClient",
    "TestGenomeRecipe",
    "anonymize_telemetry",
    "scrub_pii",
    "MeshPolicy",
    "PolicyEngine",
    "TestMesh",
]
