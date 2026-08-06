"""
End-to-End Test Suite for HarnessFleet (local_agent_sandbox.fleet).
Covers Conductor discovery, health heartbeats, affinity/DAG scheduling,
self-healing retries, node quarantine, result reconciliation, observability fingerprinting,
and CLI handlers.
"""

import os
import json
import time
import pytest
from local_agent_sandbox.fleet import (
    FleetConfig,
    NodeCapability,
    generate_default_config,
    save_config,
    load_config,
    migrate_config,
    FleetConductor,
    WorkerNode,
    NodeStatus,
    FleetScheduler,
    TestSpec,
    FleetWorker,
    FleetSelfHealingEngine,
    TestExecutionResult,
    ErrorType,
    FailureFingerprinter,
    FleetObservabilityDashboard,
    generate_trace_id,
    handle_fleet_init,
    handle_fleet_join,
    handle_fleet_run,
    handle_fleet_status,
    handle_fleet_dashboard,
    handle_fleet_migrate,
)


def test_config_serialization_and_migration(tmp_path):
    cfg = generate_default_config(cluster_name="test-cluster")
    cfg_path = str(tmp_path / "fleet.yaml")
    save_config(cfg, cfg_path)
    assert os.path.exists(cfg_path)

    loaded = load_config(cfg_path)
    assert loaded.cluster_name == "test-cluster"
    assert loaded.heartbeat_interval == 5.0

    json_path = str(tmp_path / "openharness.json")
    with open(json_path, "w") as f:
        json.dump({"cluster_name": "migrated-json-cluster", "heartbeat_interval": 10}, f)

    migrated = migrate_config(json_path)
    assert migrated.cluster_name == "migrated-json-cluster"
    assert migrated.heartbeat_interval == 10


def test_conductor_registration_and_heartbeats():
    cond = FleetConductor()

    token = cond.generate_enrollment_token(ttl=3600)
    assert cond.verify_enrollment_token(token) is True
    assert cond.verify_enrollment_token("invalid:token:sig") is False

    node = cond.register_node("127.0.0.1:9444", hostname="worker-1", token=token)
    assert node.node_id in cond.nodes
    assert node.status == NodeStatus.HEALTHY

    discovered = cond.discover_nodes(["192.168.1.10:9444", "10.0.0.5:9444"])
    assert len(discovered) == 2
    assert len(cond.nodes) == 3

    cond.record_heartbeat(node.node_id, cpu_percent=12.5, ram_percent=40.0)
    assert cond.nodes[node.node_id].cpu_percent == 12.5

    node.last_heartbeat = time.time() - 30.0
    unhealthy = cond.check_heartbeats()
    assert node.node_id in unhealthy
    assert cond.nodes[node.node_id].status == NodeStatus.UNHEALTHY


def test_scheduler_affinity_dag_and_sharding():
    scheduler = FleetScheduler()

    gpu_win_node = WorkerNode(
        node_id="node-gpu-win",
        address="10.0.0.1",
        capabilities=NodeCapability(os="windows", gpus=1, browsers=["chrome"]),
    )
    linux_node = WorkerNode(
        node_id="node-linux",
        address="10.0.0.2",
        capabilities=NodeCapability(os="linux", gpus=0, browsers=["firefox"]),
    )
    nodes = [gpu_win_node, linux_node]

    gpu_spec = TestSpec(test_id="test_gpu", file_path="t1.py", requires={"gpu": True, "os": "windows"})

    eligible = scheduler.filter_nodes_by_affinity(gpu_spec, nodes)
    assert len(eligible) == 1
    assert eligible[0].node_id == "node-gpu-win"

    t_a = TestSpec(test_id="A", file_path="a.py")
    t_b = TestSpec(test_id="B", file_path="b.py", depends_on=["A"])
    t_c = TestSpec(test_id="C", file_path="c.py", depends_on=["B"])
    t_d = TestSpec(test_id="D", file_path="d.py")

    dag_levels = scheduler.build_dag_execution_order([t_a, t_b, t_c, t_d])
    level_0_ids = {t.test_id for t in dag_levels[0]}
    assert "A" in level_0_ids and "D" in level_0_ids
    assert dag_levels[1][0].test_id == "B"
    assert dag_levels[2][0].test_id == "C"

    specs_100 = [TestSpec(test_id=f"spec_{i}", file_path=f"f_{i}.py", estimated_duration=1.0) for i in range(100)]
    shards = scheduler.split_into_shards(specs_100, num_shards=4)
    assert len(shards) == 4
    assert sum(len(s.test_specs) for s in shards) == 100
    skew = scheduler.calculate_shard_skew(shards)
    assert skew <= 0.20


def test_self_healing_and_quarantine():
    cond = FleetConductor()
    node = cond.register_node("127.0.0.1:9444")

    engine = FleetSelfHealingEngine(conductor=cond, max_infra_retries=3, quarantine_threshold=5, quarantine_window_seconds=60)

    assert engine.classify_error("AssertionError: 5 != 10") == ErrorType.ASSERTION
    assert engine.classify_error("Worker process crashed with timeout") == ErrorType.INFRASTRUCTURE

    should_retry, _ = engine.handle_test_failure("test_assert", node.node_id, "AssertionError: expected True got False")
    assert should_retry is False

    cond.register_node("127.0.0.1:9445", node_id="node-healthy-2")
    should_retry, new_node = engine.handle_test_failure("test_infra", node.node_id, "Connection refused: worker crashed")
    assert should_retry is True
    assert new_node != node.node_id

    node.infra_error_timestamps.clear()
    now = time.time()
    for _ in range(4):
        quarantined = engine.record_node_infra_error(node.node_id, timestamp=now)
        assert quarantined is False

    quarantined = engine.record_node_infra_error(node.node_id, timestamp=now)
    assert quarantined is True
    assert cond.nodes[node.node_id].status == NodeStatus.QUARANTINED

    res1 = TestExecutionResult(test_id="test_1", node_id="n1", status="PASSED", error_message="")
    assert engine.reconcile_result(res1) is True
    assert engine.reconcile_result(res1) is False
    assert engine.get_summary()["passed"] == 1


def test_observability_and_failure_fingerprinting():
    fingerprinter = FailureFingerprinter()

    failures = []
    sig1_stack = "Traceback (most recent call last):\n  File 'app/test_db.py', line 45, in test_db\n    ConnectionRefusedError: [Errno 111] Connection refused at 0x7f9a123"
    sig2_stack = "Traceback (most recent call last):\n  File 'app/test_ui.py', line 102, in test_ui\n    AssertionError: Element button-submit not found"
    sig3_stack = "Traceback (most recent call last):\n  File 'app/test_auth.py', line 12, in test_auth\n    KeyError: 'user_token_abc123'"

    for i in range(100):
        if i % 3 == 0:
            stack = f"{sig1_stack} (var_{i})"
            msg = "ConnectionRefusedError: [Errno 111]"
        elif i % 3 == 1:
            stack = f"{sig2_stack} (attempt_{i})"
            msg = "AssertionError: Element button-submit not found"
        else:
            stack = f"{sig3_stack} (id_{i})"
            msg = "KeyError: 'user_token'"

        failures.append({
            "test_id": f"test_{i}",
            "error_message": msg,
            "stack_trace": stack,
            "trace_id": generate_trace_id(),
        })

    clusters = fingerprinter.cluster_failures(failures)
    assert len(clusters) == 3
    total_clustered = sum(c.count for c in clusters)
    assert total_clustered == 100

    cond = FleetConductor()
    cond.register_node("127.0.0.1:9444")
    dash = FleetObservabilityDashboard(conductor=cond)
    dash.append_log("node-1", "INFO", "Grid initialized")
    dash.record_failure("test_failed_1", "node-1", "TimeoutError", sig1_stack)

    state = dash.render_dashboard_state()
    assert state["grid"]["total"] == 1
    assert len(state["recent_logs"]) >= 2
    assert state["total_failures"] == 1


def test_cli_fleet_handlers(tmp_path):
    yaml_out = str(tmp_path / "test_fleet.yaml")
    saved_path = handle_fleet_init(cluster_name="cli-cluster", output_path=yaml_out)
    assert os.path.exists(saved_path)

    migrated_out = str(tmp_path / "migrated_fleet.yaml")
    handle_fleet_migrate(output_path=migrated_out)
    assert os.path.exists(migrated_out)

    node = handle_fleet_join()
    assert node.node_id is not None

    status_str = handle_fleet_status()
    assert "HarnessFleet Grid Status" in status_str

    exit_code = handle_fleet_run(nodes_count=2, shards="auto", config_path=saved_path)
    assert exit_code == 0

    dash_state = handle_fleet_dashboard()
    assert "grid" in dash_state


def test_worker_execution_and_heartbeats():
    cond = FleetConductor()
    worker = FleetWorker(conductor=cond)
    assert worker.send_heartbeat() is True
    assert worker.registered is True

    res = worker.execute_test({"test_id": "test_exec_1", "file_path": "t.py"})
    assert res["status"] == "PASSED"
    assert res["test_id"] == "test_exec_1"

    cond.quarantine_node(worker.node_id)
    assert cond.nodes[worker.node_id].status == NodeStatus.QUARANTINED
    cond.unquarantine_node(worker.node_id)
    assert cond.nodes[worker.node_id].status == NodeStatus.HEALTHY


def test_scheduler_error_paths():
    scheduler = FleetScheduler()
    t1 = TestSpec(test_id="T1", file_path="t1.py", depends_on=["T2"])
    t2 = TestSpec(test_id="T2", file_path="t2.py", depends_on=["T1"])

    with pytest.raises(ValueError, match="Cyclic or unresolvable test dependencies"):
        scheduler.build_dag_execution_order([t1, t2])

    with pytest.raises(RuntimeError, match="No healthy worker nodes"):
        scheduler.schedule_execution_plan([TestSpec(test_id="X", file_path="x.py")], [])
