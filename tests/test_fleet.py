"""
End-to-End Test Suite for HarnessFleet (openharness.fleet).
Covers Conductor discovery, health heartbeats, affinity/DAG scheduling,
self-healing retries, node quarantine, result reconciliation, observability fingerprinting,
and CLI handlers.
"""

import os
import json
import time
import pytest
from openharness.fleet import (
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


def test_config_retry_strategy_parsing_and_defaults(tmp_path):
    """Config accepts retry_strategy/base_delay_ms and defaults to legacy static/immediate retry."""
    default = FleetConfig()
    assert default.retry_strategy == "static"
    assert default.base_delay_ms == 0

    cfg = FleetConfig.from_dict({"retry_strategy": "linear", "base_delay_ms": 250})
    assert cfg.retry_strategy == "linear"
    assert cfg.base_delay_ms == 250

    cfg_path = str(tmp_path / "fleet_retry.yaml")
    save_config(cfg, cfg_path)
    loaded = load_config(cfg_path)
    assert loaded.retry_strategy == "linear"
    assert loaded.base_delay_ms == 250

    from_yaml = FleetConfig.from_yaml(
        "cluster_name: legacy-cluster\nheartbeat_interval: 5.0\n"
    )
    assert from_yaml.cluster_name == "legacy-cluster"
    assert from_yaml.retry_strategy == "static"
    assert from_yaml.base_delay_ms == 0

    with pytest.raises(ValueError, match="retry_strategy"):
        FleetConfig.from_dict({"retry_strategy": "cubic"})

    with pytest.raises(ValueError, match="base_delay_ms"):
        FleetConfig.from_dict({"base_delay_ms": -5})


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
    for _ in range(5):
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

    test_file = str(tmp_path / "test_example.py")
    with open(test_file, "w", encoding="utf-8") as f:
        f.write("def test_example():\n    assert True\n")

    exit_code = handle_fleet_run(
        test_files=[test_file],
        nodes_count=2,
        shards="auto",
        config_path=saved_path,
    )
    assert exit_code == 0
    assert os.path.exists(tmp_path / ".fleet_checkpoint.json")
    assert not os.path.exists(os.path.abspath(".fleet_checkpoint.json"))

    dash_state = handle_fleet_dashboard()
    assert "grid" in dash_state


def test_worker_execution_and_heartbeats(tmp_path):
    cond = FleetConductor()
    worker = FleetWorker(conductor=cond)
    assert worker.send_heartbeat() is True
    assert worker.registered is True

    passing_test = tmp_path / "test_passing.py"
    passing_test.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    res = worker.execute_test({"test_id": "test_exec_1", "file_path": str(passing_test)})
    assert res["status"] == "PASSED"
    assert res["test_id"] == "test_exec_1"
    assert res["node_id"] == worker.node_id

    failing_test = tmp_path / "test_failing.py"
    failing_test.write_text("def test_bad():\n    assert False\n", encoding="utf-8")
    res = worker.execute_test({"test_id": "test_exec_2", "file_path": str(failing_test)})
    assert res["status"] == "FAILED"
    assert "AssertionError" in res["error_message"] or "assert" in res["stack_trace"].lower()

    missing_res = worker.execute_test({"test_id": "test_exec_3", "file_path": str(tmp_path / "missing.py")})
    assert missing_res["status"] == "INFRA_ERROR"

    cond.quarantine_node(worker.node_id)
    assert cond.nodes[worker.node_id].status == NodeStatus.QUARANTINED
    cond.unquarantine_node(worker.node_id)
    assert cond.nodes[worker.node_id].status == NodeStatus.HEALTHY


def test_worker_passes_fleet_timeout_to_pytest(monkeypatch, tmp_path):
    """The fleet run timeout must constrain the worker subprocess."""
    cond = FleetConductor()
    worker = FleetWorker(conductor=cond)
    test_file = tmp_path / "test_timeout.py"
    test_file.write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    observed = {}

    class Completed:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(*args, **kwargs):
        observed["timeout"] = kwargs["timeout"]
        return Completed()

    monkeypatch.setattr("openharness.fleet.worker.subprocess.run", fake_run)
    result = worker.execute_test(
        {"test_id": "timeout-test", "file_path": str(test_file)},
        timeout_seconds=17,
    )

    assert result["status"] == "PASSED"
    assert observed["timeout"] == 17


def test_fleet_run_real_tests_and_failures(tmp_path):
    """End-to-end: a real pytest suite runs through the fleet, with assertion failures non-retried."""
    passing = tmp_path / "test_pass.py"
    passing.write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    failing = tmp_path / "test_fail.py"
    failing.write_text("def test_bad():\n    assert False\n", encoding="utf-8")

    yaml_out = str(tmp_path / "fleet.yaml")
    handle_fleet_init(output_path=yaml_out)

    exit_code = handle_fleet_run(
        test_files=[str(passing), str(failing)],
        nodes_count=2,
        shards="auto",
        config_path=yaml_out,
    )
    assert exit_code == 1


def test_scheduler_error_paths():
    scheduler = FleetScheduler()
    t1 = TestSpec(test_id="T1", file_path="t1.py", depends_on=["T2"])
    t2 = TestSpec(test_id="T2", file_path="t2.py", depends_on=["T1"])

    with pytest.raises(ValueError, match="Cyclic or unresolvable test dependencies"):
        scheduler.build_dag_execution_order([t1, t2])

    with pytest.raises(RuntimeError, match="No healthy worker nodes"):
        scheduler.schedule_execution_plan([TestSpec(test_id="X", file_path="x.py")], [])


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
    TaskConfig,
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
    # Test default config generation and YAML round-trip
    cfg = generate_default_config(cluster_name="test-cluster")
    cfg_path = str(tmp_path / "fleet.yaml")
    save_config(cfg, cfg_path)
    assert os.path.exists(cfg_path)

    loaded = load_config(cfg_path)
    assert loaded.cluster_name == "test-cluster"
    assert loaded.heartbeat_interval == 5.0

    # Test config migration from JSON
    json_path = str(tmp_path / "openharness.json")
    with open(json_path, "w") as f:
        json.dump({"cluster_name": "migrated-json-cluster", "heartbeat_interval": 10}, f)

    migrated = migrate_config(json_path)
    assert migrated.cluster_name == "migrated-json-cluster"
    assert migrated.heartbeat_interval == 10


def test_task_config_retry_parsing_and_defaults():
    """
    Tests that task configuration schema and parsing logic accepts retry_strategy and base_delay_ms,
    defaulting to immediate/static retry behavior when omitted for backward compatibility.
    """
    # Test backward compatibility defaults when fields are omitted
    default_task_cfg = TaskConfig.from_dict({"task_id": "task-1", "name": "default-task"})
    assert default_task_cfg.retry_strategy == "immediate"
    assert default_task_cfg.base_delay_ms == 0

    default_fleet_cfg = FleetConfig.from_dict({"cluster_name": "legacy-cluster"})
    assert default_fleet_cfg.retry_strategy == "immediate"
    assert default_fleet_cfg.base_delay_ms == 0

    # Test explicit configuration parsing from dictionary (e.g. exponential or linear backoff)
    custom_dict = {
        "task_id": "task-2",
        "name": "flaky-service-task",
        "retry_strategy": "exponential",
        "base_delay_ms": 1000,
        "max_retries": 5,
    }
    parsed_task = TaskConfig.from_dict(custom_dict)
    assert parsed_task.retry_strategy == "exponential"
    assert parsed_task.base_delay_ms == 1000
    assert parsed_task.max_retries == 5

    # Test YAML parsing with retry backoff settings
    yaml_str = """
    task_id: task-3
    name: linear-backoff-task
    retry_strategy: linear
    base_delay_ms: 500
    """
    parsed_yaml = TaskConfig.from_yaml(yaml_str)
    assert parsed_yaml.task_id == "task-3"
    assert parsed_yaml.retry_strategy == "linear"
    assert parsed_yaml.base_delay_ms == 500

    # Test YAML parsing for FleetConfig with backoff settings
    fleet_yaml = """
    cluster_name: fleet-backoff-cluster
    retry_strategy: exponential
    base_delay_ms: 2500
    """
    parsed_fleet = FleetConfig.from_yaml(fleet_yaml)
    assert parsed_fleet.cluster_name == "fleet-backoff-cluster"
    assert parsed_fleet.retry_strategy == "exponential"
    assert parsed_fleet.base_delay_ms == 2500


def test_task_config_timeout_seconds_and_cli_validate(tmp_path):
    """
    Tests that task YAML parsing accepts optional timeout_seconds positive integer field,
    raises validation errors for invalid values, works with the CLI 'validate' command,
    and enforces timeout during task execution.
    """
    from local_agent_sandbox.cli import main as cli_main
    from local_agent_sandbox.orchestrator import UniverseOrchestrator

    # 1. Parsing without timeout_seconds
    cfg_default = TaskConfig.from_yaml("task_id: task-1\nname: no-timeout")
    assert cfg_default.timeout_seconds is None

    # 2. Parsing with valid positive integer timeout_seconds
    cfg_valid = TaskConfig.from_yaml("task_id: task-2\nname: custom-timeout\ntimeout_seconds: 45")
    assert cfg_valid.timeout_seconds == 45

    # 3. Invalid timeout_seconds (negative integer, zero, non-int string, bool) raise ValueError
    with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
        TaskConfig.from_dict({"task_id": "bad-1", "timeout_seconds": -10})

    with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
        TaskConfig.from_dict({"task_id": "bad-2", "timeout_seconds": 0})

    with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
        TaskConfig.from_dict({"task_id": "bad-3", "timeout_seconds": "invalid"})

    with pytest.raises(ValueError, match="timeout_seconds must be a positive integer"):
        TaskConfig.from_dict({"task_id": "bad-4", "timeout_seconds": True})

    # 4. CLI validate command success with valid YAML file containing timeout_seconds
    valid_yaml_file = tmp_path / "valid_task.yaml"
    valid_yaml_file.write_text("task_id: task-cli-1\nname: cli-test\ntimeout_seconds: 120\n")
    assert cli_main(["validate", str(valid_yaml_file)]) == 0

    # 5. CLI validate command failure with invalid YAML file
    invalid_yaml_file = tmp_path / "invalid_task.yaml"
    invalid_yaml_file.write_text("task_id: task-cli-2\nname: cli-invalid\ntimeout_seconds: -5\n")
    assert cli_main(["validate", str(invalid_yaml_file)]) == 1

    # 6. Execution engine enforcement with timeout_seconds override
    orch = UniverseOrchestrator()
    res = orch.run_task(
        command="python3 -c 'import time; time.sleep(0.05)'",
        task_config=cfg_valid,
    )
    assert res.status == "SUCCESS"
    assert res.timeout_seconds == 45


def test_conductor_registration_and_heartbeats():
    cond = FleetConductor()

    # Token generation and verification
    token = cond.generate_enrollment_token(ttl=3600)
    assert cond.verify_enrollment_token(token) is True
    assert cond.verify_enrollment_token("invalid:token:sig") is False

    # Node registration
    node = cond.register_node("127.0.0.1:9444", hostname="worker-1", token=token)
    assert node.node_id in cond.nodes
    assert node.status == NodeStatus.HEALTHY

    # Discovery
    discovered = cond.discover_nodes(["192.168.1.10:9444", "10.0.0.5:9444"])
    assert len(discovered) == 2
    assert len(cond.nodes) == 3

    # Heartbeat monitoring
    cond.record_heartbeat(node.node_id, cpu_percent=12.5, ram_percent=40.0)
    assert cond.nodes[node.node_id].cpu_percent == 12.5

    # Simulate missed heartbeats triggering UNHEALTHY
    node.last_heartbeat = time.time() - 30.0  # 30 seconds ago (interval=5, 6 missed)
    unhealthy = cond.check_heartbeats()
    assert node.node_id in unhealthy
    assert cond.nodes[node.node_id].status == NodeStatus.UNHEALTHY


def test_scheduler_affinity_dag_and_sharding():
    scheduler = FleetScheduler()

    # Create worker nodes with heterogeneous capabilities
    gpu_win_node = WorkerNode(
        node_id="node-gpu-win",
        address="10.0.0.1",
        capabilities=NodeCapability(os="windows", gpus=1, browsers=["chrome"]),
    )
    cpu_linux_node = WorkerNode(
        node_id="node-cpu-lin",
        address="10.0.0.2",
        capabilities=NodeCapability(os="linux", gpus=0, browsers=["firefox", "chrome"]),
    )
    nodes = {gpu_win_node.node_id: gpu_win_node, cpu_linux_node.node_id: cpu_linux_node}

    # Define tests with constraints
    t1 = TestSpec(test_id="test-gpu-win", file_path="tests/test_gpu.py", required_gpus=1, required_os="windows")
    t2 = TestSpec(test_id="test-linux-browser", file_path="tests/test_ui.py", required_browser="firefox")
    t3 = TestSpec(test_id="test-dag-child", file_path="tests/test_child.py", dependencies=["test-gpu-win"])

    # Node affinity resolution
    assigned_node_1 = scheduler.select_optimal_node(t1, nodes)
    assert assigned_node_1 == "node-gpu-win"

    assigned_node_2 = scheduler.select_optimal_node(t2, nodes)
    assert assigned_node_2 == "node-cpu-lin"

    # Dynamic Sharding
    specs = [t1, t2, t3]
    shards = scheduler.shard_workload(specs, num_shards=2, strategy="balanced")
    assert len(shards) == 2
    assert sum(len(s) for s in shards) == 3

    # DAG Dependency topological sorting
    sorted_specs = scheduler.resolve_dag_execution_order(specs)
    t1_idx = next(i for i, s in enumerate(sorted_specs) if s.test_id == "test-gpu-win")
    t3_idx = next(i for i, s in enumerate(sorted_specs) if s.test_id == "test-dag-child")
    assert t1_idx < t3_idx


def test_fleet_worker_and_self_healing_retries():
    cond = FleetConductor()
    worker = FleetWorker(conductor=cond, address="127.0.0.1:9445")
    node = worker.join()
    assert node.node_id in cond.nodes

    # Heartbeat emission
    assert worker.send_heartbeat(cpu_percent=10.0, ram_percent=20.0) is True

    # Test execution simulation
    result_dict = worker.execute_test({"test_id": "t-100", "file_path": "tests/test_basic.py"})
    assert result_dict["status"] == "PASSED"
    assert result_dict["test_id"] == "t-100"

    # Self-Healing Retry Engine
    healer = FleetSelfHealingEngine(max_retries=2)
    spec = TestSpec(test_id="t-flaky", file_path="tests/test_flaky.py")

    # Transient error should trigger retry
    fail_res = TestExecutionResult(
        test_id="t-flaky",
        node_id="worker-1",
        status="FAILED",
        error_type=ErrorType.NETWORK_FLAKE,
        error_message="Connection reset by peer",
        duration_seconds=0.5,
        file_path="tests/test_flaky.py",
    )
    should_retry, retry_spec = healer.evaluate_retry(spec, fail_res)
    assert should_retry is True
    assert retry_spec.retry_count == 1

    # Max retries exceeded
    fail_res_2 = TestExecutionResult(
        test_id="t-flaky",
        node_id="worker-1",
        status="FAILED",
        error_type=ErrorType.NETWORK_FLAKE,
        error_message="Connection reset by peer",
        duration_seconds=0.5,
        file_path="tests/test_flaky.py",
    )
    should_retry_2, _ = healer.evaluate_retry(retry_spec, fail_res_2)
    assert should_retry_2 is True

    retry_spec_2 = TestSpec(test_id="t-flaky", file_path="tests/test_flaky.py", retry_count=2)
    should_retry_3, _ = healer.evaluate_retry(retry_spec_2, fail_res_2)
    assert should_retry_3 is False  # Reached max retries (2)


def test_failure_fingerprinting_and_dashboard():
    fingerprinter = FailureFingerprinter()

    res_infra = TestExecutionResult(
        test_id="t-1",
        node_id="n-1",
        status="FAILED",
        error_type=ErrorType.INFRA_CRASH,
        error_message="OOMKilled worker container",
    )
    res_code = TestExecutionResult(
        test_id="t-2",
        node_id="n-2",
        status="FAILED",
        error_type=ErrorType.TEST_FAILURE,
        error_message="AssertionError: expected 200 got 500",
    )

    fingerprinter.record_result(res_infra)
    fingerprinter.record_result(res_code)

    summary = fingerprinter.get_summary()
    assert summary["total_results"] == 2
    assert summary["failed_results"] == 2
    assert "INFRA_CRASH" in summary["error_counts"]
    assert "TEST_FAILURE" in summary["error_counts"]

    # Dashboard observability render
    dashboard = FleetObservabilityDashboard(fingerprinter=fingerprinter)
    metric = dashboard.record_run_metric(trace_id="tr-1234", duration_seconds=12.5, pass_rate=50.0)
    assert metric["trace_id"] == "tr-1234"

    render_text = dashboard.render_cli_dashboard()
    assert "HarnessFleet Real-Time Observability Grid" in render_text
    assert "INFRA_CRASH" in render_text


def test_fleet_cli_handlers():
    # CLI handler invocations
    assert handle_fleet_init(cluster_name="cli-test-fleet", output_path="fleet_test_init.yaml").endswith("fleet_test_init.yaml")
    if os.path.exists("fleet_test_init.yaml"):
        os.remove("fleet_test_init.yaml")

    assert handle_fleet_migrate(output_path="fleet_test_migrated.yaml").endswith("fleet_test_migrated.yaml")
    if os.path.exists("fleet_test_migrated.yaml"):
        os.remove("fleet_test_migrated.yaml")

    assert handle_fleet_join(conductor_address="127.0.0.1:9443") is True
    assert handle_fleet_run(test_files=["tests/test_sample.py"]) == 0
    assert handle_fleet_status() == 0
    assert handle_fleet_dashboard() == 0
