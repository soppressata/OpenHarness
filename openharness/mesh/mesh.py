"""
TestMesh orchestrator — ties discovery, scheduling, cortex, black box,
commons, and policy into a single entry point.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from openharness.mesh.blackbox import BlackBoxRecorder, BlackBoxRecording, delta_diff, replay_recording
from openharness.mesh.commons import CommonsClient, TestGenomeRecipe
from openharness.mesh.cortex import CortexEngine, QuarantineDecision, TestRunOutcome
from openharness.mesh.discovery import PeerInfo, PeerRegistry, RendezvousStore
from openharness.mesh.identity import PeerIdentity
from openharness.mesh.manifest import (
    AirGappedBundle,
    RunManifest,
    SuiteResult,
    create_run_manifest,
    dual_sign_manifest,
    execute_airgapped_bundle,
    pack_airgapped_bundle,
    verify_manifest,
    write_manifest,
)
from openharness.mesh.policy import MeshPolicy, PolicyEngine
from openharness.mesh.scheduler import MeshScheduler


class TestMesh:
    """Federated Test Mesh node.

    Example (two clusters on one laptop)::

        store = RendezvousStore("/tmp/mesh-dht")
        a = TestMesh(PeerIdentity.generate(region="us-east"), store, policy=MeshPolicy(telemetry_consent=False))
        b = TestMesh(PeerIdentity.generate(region="eu-west"), store)
        a.advertise_suite("suite-1", name="payments")
        peers = a.discover_peers()
        manifest = a.run_on_peer(b, "suite-1", results=[...])
    """

    __test__ = False

    def __init__(
        self,
        identity: Optional[PeerIdentity] = None,
        rendezvous: Optional[RendezvousStore | str | Path] = None,
        policy: Optional[MeshPolicy] = None,
        commons_root: Optional[str | Path] = None,
    ):
        self.identity = identity or PeerIdentity.generate()
        if isinstance(rendezvous, RendezvousStore):
            self.store = rendezvous
        else:
            root = Path(rendezvous) if rendezvous else Path(".openharness/mesh/dht")
            self.store = RendezvousStore(root)
        self.policy = policy or MeshPolicy(project_id=self.identity.cluster_id)
        self.policy_engine = PolicyEngine(self.policy, self.identity)
        self.registry = PeerRegistry(self.identity, self.store)
        self.scheduler = MeshScheduler(self.identity)
        self.cortex = CortexEngine(identity=self.identity)
        commons_path = Path(commons_root) if commons_root else Path(".openharness/mesh/commons")
        self.commons = CommonsClient(
            commons_path,
            project_id=self.policy.project_id,
            identity=self.identity,
            consent=self.policy.telemetry_consent,
        )
        self.manifests: List[RunManifest] = []
        self.recordings: List[BlackBoxRecording] = []

    def announce(self, **kwargs: Any) -> PeerInfo:
        """Announce this node to the mesh."""
        return self.registry.announce(**kwargs)

    def advertise_suite(self, suite_id: str, name: str = "", metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self.registry.advertise_suite(suite_id, name=name, metadata=metadata)

    def discover_peers(self) -> List[PeerInfo]:
        peers = self.registry.discover_peers()
        return self.policy_engine.filter_peers(peers)

    def select_executor(
        self,
        required_capabilities: Optional[Dict[str, Any]] = None,
    ) -> Optional[PeerInfo]:
        """Geo-optimal peer selection among policy-approved peers (AC-8)."""
        peers = self.discover_peers()
        return self.scheduler.select_peer(peers, required_capabilities=required_capabilities)

    def run_on_peer(
        self,
        executor: "TestMesh | PeerIdentity",
        suite_id: str,
        results: Sequence[SuiteResult | Dict[str, Any]],
        suite_name: str = "",
    ) -> RunManifest:
        """Schedule a suite on a remote peer identity and dual-sign the manifest (AC-6)."""
        if isinstance(executor, TestMesh):
            exec_identity = executor.identity
        else:
            exec_identity = executor

        peer_info = PeerInfo(
            peer_id=exec_identity.peer_id,
            cluster_id=exec_identity.cluster_id,
            region=exec_identity.region,
            capabilities=dict(exec_identity.capabilities),
        )
        decision = self.policy_engine.check_peer(peer_info)
        if not decision.allowed:
            raise PermissionError(f"policy denied remote run: {decision.reason}")

        normalized: List[SuiteResult] = []
        for r in results:
            if isinstance(r, SuiteResult):
                normalized.append(r)
            else:
                normalized.append(SuiteResult(**r))

        manifest = self.scheduler.schedule_remote(
            suite_id=suite_id,
            executor=exec_identity,
            results=normalized,
            suite_name=suite_name,
        )
        self.manifests.append(manifest)

        # Feed cortex
        for r in normalized:
            self.cortex.record(
                TestRunOutcome(
                    test_id=r.test_id,
                    passed=r.status == "passed",
                    environment=self.identity.region,
                )
            )

        if self.policy.telemetry_consent:
            self.commons.consent = True
            self.commons.contribute_telemetry(
                {
                    "suite_id": suite_id,
                    "result_count": len(normalized),
                    "passed": sum(1 for r in normalized if r.status == "passed"),
                }
            )
        return manifest

    def pack_airgapped(
        self,
        suite_id: str,
        tests: List[Dict[str, Any]],
        suite_name: str = "",
    ) -> AirGappedBundle:
        decision = self.policy_engine.check_airgapped_export()
        if not decision.allowed:
            raise PermissionError(decision.reason)
        return pack_airgapped_bundle(suite_id, tests, self.identity, suite_name=suite_name)

    def execute_airgapped(self, bundle: AirGappedBundle) -> RunManifest:
        manifest = execute_airgapped_bundle(bundle, self.identity)
        self.manifests.append(manifest)
        return manifest

    def capture(self, test_id: str) -> BlackBoxRecorder:
        return BlackBoxRecorder(identity=self.identity, test_id=test_id)

    def replay(self, recording: BlackBoxRecording) -> BlackBoxRecording:
        return replay_recording(recording)

    def diff_recordings(self, a: BlackBoxRecording, b: BlackBoxRecording) -> Dict[str, Any]:
        return delta_diff(a, b)

    def record_outcome(self, outcome: TestRunOutcome) -> Optional[QuarantineDecision]:
        return self.cortex.record(outcome)

    def reorder_tests(self, tests: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return self.cortex.predictive_reorder(tests)

    def publish_recipe(self, recipe: TestGenomeRecipe) -> str:
        return self.commons.publish_recipe(recipe)

    def recommendations(self, project_pattern: Dict[str, Any]) -> List[Dict[str, Any]]:
        return self.commons.recommend(project_pattern)

    def opt_out_commons(self) -> Dict[str, Any]:
        return self.commons.opt_out(purge=True)

    def emit_signed_run_manifest(
        self,
        suite_id: str,
        results: Sequence[SuiteResult | Dict[str, Any]],
        suite_name: str = "",
        path: Optional[str | Path] = None,
    ) -> RunManifest:
        """Phase 0 exit: emit a signed run manifest for a local execution."""
        normalized = [
            r if isinstance(r, SuiteResult) else SuiteResult(**r) for r in results
        ]
        manifest = create_run_manifest(suite_id, self.identity, suite_name=suite_name)
        manifest = dual_sign_manifest(manifest, self.identity, normalized)
        self.manifests.append(manifest)
        if path is not None:
            write_manifest(path, manifest)
        return manifest

    def health(self) -> Dict[str, Any]:
        """Operator dashboard snapshot (AC-23)."""
        return {
            "peer_id": self.identity.peer_id,
            "cluster_id": self.identity.cluster_id,
            "region": self.identity.region,
            "peers_visible": len(self.discover_peers()),
            "suites_advertised": len(self.registry._local_suites),
            "quarantine_decisions": len(self.cortex.decisions),
            "quarantined_tests": sum(
                1 for s in self.cortex._stats.values() if s.quarantined
            ),
            "telemetry_consent": self.policy.telemetry_consent,
            "manifests_emitted": len(self.manifests),
            "recordings": len(self.recordings),
            "policy_decisions": len(self.policy_engine.decisions),
        }
