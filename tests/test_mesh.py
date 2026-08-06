"""
Tests for the OpenHarness Cross-Boundary Test Mesh.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from openharness.cli.main import cli
from openharness.mesh import (
    AirGappedBundle,
    BlackBoxRecorder,
    CommonsClient,
    CortexEngine,
    MeshPolicy,
    PeerIdentity,
    PeerRegistry,
    PolicyEngine,
    RendezvousStore,
    RunManifest,
    SuiteResult,
    TestGenomeRecipe,
    TestMesh,
    TestRunOutcome,
    anonymize_telemetry,
    create_run_manifest,
    delta_diff,
    dual_sign_manifest,
    execute_airgapped_bundle,
    make_event,
    pack_airgapped_bundle,
    replay_recording,
    scrub_pii,
    select_geo_optimal_peer,
    verify_event,
    verify_manifest,
)
from openharness.mesh.discovery import PeerInfo
from openharness.mesh.events import EventType


def test_signed_event_roundtrip():
    peer = PeerIdentity.generate(cluster_id="c1", region="us-east")
    event = make_event(EventType.RUN_COMPLETED, peer, payload={"suite": "s1"})
    assert event.signature
    assert verify_event(event, peer)
    other = PeerIdentity.generate()
    assert not verify_event(event, other)


def test_dual_signed_manifest_third_party_verifiable():
    origin = PeerIdentity.generate(cluster_id="org-a", region="us-east")
    executor = PeerIdentity.generate(cluster_id="org-b", region="eu-west")
    manifest = create_run_manifest("suite-x", origin, suite_name="X")
    manifest = dual_sign_manifest(
        manifest,
        executor,
        [SuiteResult(test_id="t1", status="passed"), SuiteResult(test_id="t2", status="failed", message="boom")],
    )
    ok, errors = verify_manifest(
        manifest,
        origin.export_verification_material(),
        executor.export_verification_material(),
    )
    assert ok, errors
    assert manifest.origin_peer_id == origin.peer_id
    assert manifest.executor_peer_id == executor.peer_id
    # Tamper detection
    manifest.results[0].status = "skipped"
    ok2, errors2 = verify_manifest(
        manifest,
        origin.export_verification_material(),
        executor.export_verification_material(),
    )
    assert not ok2
    assert "executor_signature_invalid" in errors2


def test_peer_discovery_without_coordinator(tmp_path):
    store = RendezvousStore(tmp_path / "dht")
    a = PeerRegistry(PeerIdentity.generate(cluster_id="a", region="us-east"), store)
    b = PeerRegistry(PeerIdentity.generate(cluster_id="b", region="eu-west"), store)
    a.advertise_suite("suite-1", name="payments")
    b.advertise_suite("suite-2", name="billing")
    a.announce()
    b.announce()

    peers_from_a = a.discover_peers()
    peers_from_b = b.discover_peers()
    assert len(peers_from_a) == 1
    assert peers_from_a[0].peer_id == b.identity.peer_id
    assert len(peers_from_b) == 1
    assert any(s.get("suite_id") == "suite-1" for s in a.discover_suites())
    assert any(s.get("suite_id") == "suite-2" for s in b.discover_suites())


def test_airgapped_bundle_offline_execution(tmp_path):
    origin = PeerIdentity.generate(cluster_id="air-origin")
    executor = PeerIdentity.generate(cluster_id="air-exec")
    bundle = pack_airgapped_bundle(
        "offline-suite",
        [{"id": "t1"}, {"id": "t2", "fail": True}],
        origin,
        suite_name="Offline",
    )
    assert origin.verify_payload(bundle.body_for_signing(), bundle.origin_signature)

    path = tmp_path / "bundle.json"
    path.write_text(bundle.model_dump_json(), encoding="utf-8")
    loaded = AirGappedBundle(**json.loads(path.read_text(encoding="utf-8")))

    manifest = execute_airgapped_bundle(
        loaded,
        executor,
        origin_material=origin.export_verification_material(),
        origin=origin,
    )
    assert len(manifest.results) == 2
    assert manifest.results[0].status == "passed"
    assert manifest.results[1].status == "failed"
    ok, errors = verify_manifest(
        manifest,
        origin.export_verification_material(),
        executor.export_verification_material(),
    )
    assert ok, errors


def test_geo_optimal_peer_selection():
    peers = [
        PeerInfo(
            peer_id="p-east",
            cluster_id="c1",
            region="us-east",
            capabilities={"os": "linux", "gpu": False},
            latency_ms_estimate=80.0,
        ),
        PeerInfo(
            peer_id="p-west",
            cluster_id="c2",
            region="us-west",
            capabilities={"os": "linux", "gpu": False},
            latency_ms_estimate=10.0,
        ),
        PeerInfo(
            peer_id="p-eu",
            cluster_id="c3",
            region="eu-west",
            capabilities={"os": "linux", "gpu": False},
            latency_ms_estimate=5.0,
        ),
    ]
    # Origin in us-west should prefer us-west peer among identical capabilities
    chosen = select_geo_optimal_peer("us-west", peers, required_capabilities={"os": "linux", "gpu": False})
    assert chosen is not None
    assert chosen.peer_id == "p-west"


def test_cortex_auto_quarantine_and_promote():
    cortex = CortexEngine(
        quarantine_inconsistent_runs=5,
        promotion_clean_runs=3,
        flake_confidence_threshold=0.5,
    )
    decision = None
    # Alternating outcomes → inconsistent
    for i in range(5):
        decision = cortex.record(TestRunOutcome(test_id="flaky", passed=(i % 2 == 0)))
    assert decision is not None
    assert decision.action == "quarantine"
    assert decision.confidence >= 0.5
    assert decision.attestation is not None
    assert cortex.is_quarantined("flaky")

    # Clean runs → promote after N statistically significant clean runs
    promote = None
    for _ in range(3):
        maybe = cortex.record(TestRunOutcome(test_id="flaky", passed=True))
        if maybe is not None:
            promote = maybe
    assert promote is not None
    assert promote.action == "promote"
    assert not cortex.is_quarantined("flaky")
    assert all(d.event_id for d in cortex.decisions)


def test_predictive_reorder_surfaces_failures_earlier():
    cortex = CortexEngine()
    # Historical: slow_pass always passes, fast_fail always fails
    for _ in range(5):
        cortex.record(TestRunOutcome(test_id="slow_pass", passed=True))
        cortex.record(TestRunOutcome(test_id="fast_fail", passed=False))

    tests = [
        {"id": "slow_pass", "duration_ms": 1000.0, "will_fail": False},
        {"id": "fast_fail", "duration_ms": 10.0, "will_fail": True},
        {"id": "unknown", "duration_ms": 50.0, "will_fail": False},
    ]
    fifo_time = 0.0
    for t in tests:
        fifo_time += t["duration_ms"]
        if t["will_fail"]:
            break

    ordered = cortex.predictive_reorder(tests)
    pred_time = cortex.median_first_failure_time(ordered)
    assert ordered[0]["id"] == "fast_fail"
    assert pred_time is not None
    assert pred_time < fifo_time


def test_blackbox_replay_identical_and_delta_diff():
    peer = PeerIdentity.generate()
    rec = BlackBoxRecorder(identity=peer, test_id="bb1")
    rec.syscall("open", path="/tmp/a")
    rec.network("connect", host="10.0.0.1", port=443)
    rec.file_op("write", path="/tmp/a", bytes=12)
    original = rec.finalize(output={"ok": True}, passed=True)

    replayed = replay_recording(original)
    diff = delta_diff(original, replayed)
    assert diff["identical"] is True
    assert diff["cause"] == "none"
    assert original.schema_version == replayed.schema_version

    # Inject drift on replay
    def drift(ev):
        if ev.name == "connect":
            return "connection refused"
        return None

    drifted = replay_recording(original, event_handler=drift)
    d2 = delta_diff(original, drifted)
    assert d2["identical"] is False
    assert d2["first_divergence_index"] == 1
    assert d2["cause"] in ("network", "data")


def test_commons_pii_scrub_recipes_recommend_opt_out(tmp_path):
    raw = {
        "message": "user jane@example.com from 192.168.1.1 token=abc123",
        "note": "API_KEY=sk-secret Bearer eyJhbGciOiJIUzI1NiJ9.xx",
    }
    scrubbed_msg = scrub_pii(raw["message"])
    assert "jane@example.com" not in scrubbed_msg
    assert "192.168.1.1" not in scrubbed_msg
    anon = anonymize_telemetry(raw, project_id="proj-1")
    assert anon["pii_scrubbed"] is True
    assert "jane@example.com" not in json.dumps(anon)

    client = CommonsClient(tmp_path / "commons", project_id="proj-1", consent=True)
    entry = client.contribute_telemetry(raw)
    assert entry is not None
    assert (tmp_path / "commons" / "telemetry" / f"{entry}.json").exists()

    recipe = TestGenomeRecipe(
        name="user-service-fixtures",
        version="1.0.0",
        pattern={"suite": "UserService", "fixture": "db"},
        tags=["service", "fixtures"],
        metrics={"runtime_reduction_pct": 43},
    )
    client.publish_recipe(recipe)
    installed = client.install_recipe("user-service-fixtures", "1.0.0", tmp_path / "installed")
    assert Path(installed).exists()

    tips = client.recommend({"suite": "UserService", "tags": ["service"], "pattern": {"suite": "UserService"}})
    assert tips
    assert tips[0]["score"] > 0

    result = client.opt_out(purge=True)
    assert result["opted_out"] is True
    assert result["within_24h"] is True
    assert not (tmp_path / "commons" / "telemetry" / f"{entry}.json").exists()


def test_policy_enforcement():
    policy = MeshPolicy(
        project_id="p1",
        telemetry_consent=False,
        allowed_regions=["us-east"],
        denied_peer_ids=["bad-peer"],
        data_residency="region",
        allow_remote_execution=True,
    )
    engine = PolicyEngine(policy)
    assert not engine.check_telemetry().allowed

    good = PeerInfo(peer_id="good", cluster_id="c", region="us-east")
    bad_region = PeerInfo(peer_id="x", cluster_id="c", region="eu-west")
    denied = PeerInfo(peer_id="bad-peer", cluster_id="c", region="us-east")
    assert engine.check_peer(good).allowed
    assert not engine.check_peer(bad_region).allowed
    assert not engine.check_peer(denied).allowed


def test_testmesh_end_to_end_federated(tmp_path):
    store = RendezvousStore(tmp_path / "dht")
    policy = MeshPolicy(project_id="a", telemetry_consent=True, data_residency="global", allowed_regions=["*"])
    a = TestMesh(
        PeerIdentity.generate(cluster_id="org-a", region="us-east", capabilities={"os": "linux"}),
        rendezvous=store,
        policy=policy,
        commons_root=tmp_path / "commons",
    )
    b = TestMesh(
        PeerIdentity.generate(cluster_id="org-b", region="eu-west", capabilities={"os": "linux"}),
        rendezvous=store,
        policy=MeshPolicy(project_id="b", data_residency="global"),
        commons_root=tmp_path / "commons",
    )
    a.announce(latency_ms_estimate=5)
    b.announce(latency_ms_estimate=20)
    a.advertise_suite("s1", name="Suite One")

    assert len(a.discover_peers()) == 1
    selected = a.select_executor(required_capabilities={"os": "linux"})
    assert selected is not None
    assert selected.peer_id == b.identity.peer_id

    manifest = a.run_on_peer(
        b,
        "s1",
        [SuiteResult(test_id="t1", status="passed")],
        suite_name="Suite One",
    )
    ok, errors = verify_manifest(
        manifest,
        a.identity.export_verification_material(),
        b.identity.export_verification_material(),
    )
    assert ok, errors

    # Phase 0 local signed manifest
    local = a.emit_signed_run_manifest("local-suite", [{"test_id": "l1", "status": "passed"}], path=tmp_path / "m.json")
    assert (tmp_path / "m.json").exists()
    assert local.origin_signature and local.executor_signature

    health = a.health()
    assert health["peers_visible"] == 1
    assert health["manifests_emitted"] >= 2
    assert "telemetry_consent" in health


def test_secrets_never_in_public_export():
    peer = PeerIdentity.generate()
    public = peer.export_public()
    assert "secret" not in json.dumps(public).lower()
    event = make_event(EventType.PEER_ANNOUNCE, peer, payload=public)
    audit = event.to_audit_record()
    assert "secret_hex" not in json.dumps(audit)


def test_cli_mesh_demo_and_manifest(tmp_path):
    runner = CliRunner()
    result = runner.invoke(cli, ["mesh", "demo", "--root", str(tmp_path / "demo")])
    assert result.exit_code == 0, result.output
    assert "Mesh demo complete" in result.output
    assert "Dual-signed manifest" in result.output

    out = tmp_path / "man.json"
    result2 = runner.invoke(
        cli,
        ["mesh", "manifest", "--suite-id", "s-cli", "--out", str(out), "--region", "us-east"],
    )
    assert result2.exit_code == 0, result2.output
    assert out.exists()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["origin_signature"]
    assert data["executor_signature"]
