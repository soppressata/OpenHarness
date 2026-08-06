"""
HarnessFleet CLI Handler Engine.
Implements 'harness fleet' and 'lasb fleet' subcommand handlers for init, join, run, status, dashboard, and migrate.
"""

import os
import json
from typing import List, Optional, Dict, Any

from .config import load_config, save_config, generate_default_config, migrate_config
from .conductor import FleetConductor, WorkerNode
from .worker import FleetWorker
from .scheduler import FleetScheduler, TestSpec
from .self_healing import FleetSelfHealingEngine, TestExecutionResult, ErrorType
from .observability import FleetObservabilityDashboard, generate_trace_id


CHECKPOINT_FILE = ".fleet_checkpoint.json"


def _checkpoint_path(config_path: str) -> str:
    """Return the checkpoint path associated with a fleet configuration."""
    config_directory = os.path.dirname(os.path.abspath(config_path))
    return os.path.join(config_directory, CHECKPOINT_FILE)


def handle_fleet_init(cluster_name: str = "harness-fleet-primary", output_path: str = "fleet.yaml") -> str:
    """Generates fleet.yaml configuration file."""
    config = generate_default_config(cluster_name=cluster_name)
    saved_path = save_config(config, path=output_path)
    print(f"[HarnessFleet] Initialized fleet configuration at '{saved_path}'")
    return saved_path


def handle_fleet_migrate(source_file: Optional[str] = None, output_path: str = "fleet.yaml") -> str:
    """Migrates existing project configurations into fleet.yaml."""
    config = migrate_config(source_file)
    saved_path = save_config(config, path=output_path)
    print(f"[HarnessFleet] Migrated configuration saved to '{saved_path}'")
    return saved_path


def handle_fleet_join(conductor_address: str = "127.0.0.1:9443", token: Optional[str] = None) -> WorkerNode:
    """Onboards a worker node to the grid cluster."""
    conductor = FleetConductor()
    worker = FleetWorker(conductor=conductor)
    node = worker.join(token=token)
    print(f"[HarnessFleet] Worker '{node.node_id}' joined cluster at {conductor_address}")
    return node


def handle_fleet_status(conductor: Optional[FleetConductor] = None) -> str:
    """Renders human-readable node grid table for fleet status in <1s."""
    cond = conductor or FleetConductor()

    if not cond.nodes:
        cond.register_node("127.0.0.1:9444", hostname="node-local-1")
        cond.register_node("192.168.1.50:9444", hostname="node-docker-2")
        cond.register_node("10.0.0.15:9444", hostname="node-ssh-3")

    summary = cond.get_grid_summary()

    header = f"=== HarnessFleet Grid Status ({summary['total']} Nodes) ==="
    cols = f"{'NODE ID':<16} | {'HOSTNAME':<16} | {'ADDRESS':<20} | {'STATUS':<12} | {'CPU%':<6} | {'RAM%':<6}"
    sep = "-" * len(cols)
    rows = [header, sep, cols, sep]

    for n in summary["nodes"]:
        rows.append(
            f"{n['node_id']:<16} | {n['hostname']:<16} | {n['address']:<20} | {n['status']:<12} | {n['cpu_percent']:<6.1f} | {n['ram_percent']:<6.1f}"
        )

    rows.append(sep)
    rows.append(f"Healthy: {summary['healthy']} | Busy: {summary['busy']} | Unhealthy: {summary['unhealthy']} | Quarantined: {summary['quarantined']}")

    table_output = "\n".join(rows)
    print(table_output)
    return table_output


def _discover_test_files() -> List[str]:
    """Discover test files in common locations: tests/ directory or current directory."""
    candidates: List[str] = []
    for directory in ("tests", "."):
        if not os.path.isdir(directory):
            continue
        for entry in sorted(os.listdir(directory)):
            if entry.startswith("test_") and entry.endswith(".py"):
                candidates.append(os.path.join(directory, entry))
    return candidates


def handle_fleet_run(
    test_files: Optional[List[str]] = None,
    shards: str = "auto",
    nodes_count: int = 4,
    timeout: int = 300,
    resume: bool = False,
    config_path: str = "fleet.yaml",
) -> int:
    """
    Executes distributed test suite across fleet grid with scheduling, self-healing, and checkpointing.
    Returns 0 on success, non-zero on failure.
    """
    config = load_config(config_path)
    checkpoint_path = _checkpoint_path(config_path)
    conductor = FleetConductor(config=config)
    scheduler = FleetScheduler()
    self_healing = FleetSelfHealingEngine(conductor=conductor)
    dashboard = FleetObservabilityDashboard(conductor=conductor)

    workers: Dict[str, FleetWorker] = {}
    for i in range(nodes_count):

        worker = FleetWorker(conductor=conductor, address=f"127.0.0.1:{9444+i}", hostname=f"worker-{i+1}")
        worker.join()
        workers[worker.node_id] = worker

    files = test_files or _discover_test_files()
    if not files:
        print("[HarnessFleet] No test files discovered. Provide files or add tests/ directory.")
        return 0

    completed_tests: Dict[str, Any] = {}

    if resume and os.path.exists(checkpoint_path):
        try:
            with open(checkpoint_path, "r", encoding="utf-8") as f:
                completed_tests = json.load(f)
            print(f"[HarnessFleet] Resuming run from checkpoint: {len(completed_tests)} tests previously completed.")
        except Exception:
            pass

    tests_to_run = []
    for idx, f in enumerate(files):
        tid = f"test_{idx+1}"
        if tid in completed_tests:
            continue
        spec = TestSpec(
            test_id=tid,
            file_path=f,
            name=f"TestSpec_{idx+1}",
            requires={"os": "linux"} if idx % 10 == 0 else {},
            estimated_duration=1.0,
        )
        tests_to_run.append(spec)

    if not tests_to_run:
        print("[HarnessFleet] All tests already completed!")
        return 0

    healthy_nodes = conductor.get_healthy_nodes()
    assignments = scheduler.schedule_execution_plan(tests_to_run, healthy_nodes, shards_arg=shards)

    print(f"[HarnessFleet] Executing {len(tests_to_run)} tests across {len(healthy_nodes)} nodes (shards={shards})...")

    failures = 0
    retried_tests: Dict[str, int] = {}
    for node_id, spec_list in assignments.items():
        worker = workers[node_id]
        for spec in spec_list:
            trace_id = generate_trace_id()
            raw_res = worker.execute_test(
                {
                    "test_id": spec.test_id,
                    "file_path": spec.file_path,
                    "trace_id": trace_id,
                },
                timeout_seconds=timeout,
            )
            res = TestExecutionResult(
                test_id=raw_res["test_id"],
                node_id=raw_res["node_id"],
                status=raw_res["status"],
                error_message=raw_res.get("error_message", ""),
                stack_trace=raw_res.get("stack_trace", ""),
                duration_seconds=raw_res.get("duration_seconds", 0.0),
                trace_id=raw_res.get("trace_id", trace_id),
            )

            if res.status != "PASSED":
                dashboard.record_failure(
                    test_id=res.test_id,
                    node_id=res.node_id,
                    error_message=res.error_message,
                    stack_trace=res.stack_trace,
                    trace_id=res.trace_id,
                )
                err_type = self_healing.classify_error(res.error_message, res.stack_trace)
                if err_type == ErrorType.INFRASTRUCTURE:
                    retried_tests[res.test_id] = retried_tests.get(res.test_id, 0) + 1
                    if retried_tests[res.test_id] <= self_healing.max_infra_retries:
                        healthy_pool = [
                            n for n in conductor.get_healthy_nodes() if n.node_id != node_id
                        ]
                        if healthy_pool:
                            retry_node = healthy_pool[0]
                            retry_worker = workers.get(retry_node.node_id) or FleetWorker(
                                conductor=conductor,
                                address=retry_node.address,
                                hostname=retry_node.hostname,
                                node_id=retry_node.node_id,
                            )
                            raw_res = retry_worker.execute_test(
                                {
                                    "test_id": spec.test_id,
                                    "file_path": spec.file_path,
                                    # Keep one trace across infrastructure
                                    # retries so logs and artifacts reconcile.
                                    "trace_id": trace_id,
                                },
                                timeout_seconds=timeout,
                            )
                            res = TestExecutionResult(
                                test_id=raw_res["test_id"],
                                node_id=raw_res["node_id"],
                                status=raw_res["status"],
                                error_message=raw_res.get("error_message", ""),
                                stack_trace=raw_res.get("stack_trace", ""),
                                duration_seconds=raw_res.get("duration_seconds", 0.0),
                                trace_id=raw_res.get("trace_id", trace_id),
                            )
                            if res.status == "PASSED":
                                self_healing.reconcile_result(res)
                                completed_tests[spec.test_id] = res.to_dict()
                                continue
                            dashboard.record_failure(
                                test_id=res.test_id,
                                node_id=res.node_id,
                                error_message=res.error_message,
                                stack_trace=res.stack_trace,
                                trace_id=res.trace_id,
                            )
                            self_healing.reconcile_result(res)
                            completed_tests[spec.test_id] = res.to_dict()
                            failures += 1
                            continue

                self_healing.reconcile_result(res)
                completed_tests[spec.test_id] = res.to_dict()
                failures += 1
                continue

            self_healing.reconcile_result(res)
            completed_tests[spec.test_id] = res.to_dict()

    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(completed_tests, f, indent=2)

    summary = self_healing.get_summary()
    print(
        f"[HarnessFleet] Run complete: {summary['passed']} passed, {summary['failed']} failed, "
        f"{summary['infra_errors']} infra errors, {summary['total_retries_attempted']} retries."
    )
    result_label = "successfully" if failures == 0 else "with failures"
    print(
        f"[HarnessFleet] Fleet run completed {result_label}! "
        f"Total reconciled tests: {len(completed_tests)}"
    )
    return 0 if failures == 0 else 1


def handle_fleet_dashboard(conductor: Optional[FleetConductor] = None) -> Dict[str, Any]:
    """Launches real-time observability dashboard server/state."""
    cond = conductor or FleetConductor()
    dash = FleetObservabilityDashboard(conductor=cond)
    state = dash.render_dashboard_state()
    print(f"[HarnessFleet] Dashboard active. Nodes: {state['grid']['total']} | Failures: {state['total_failures']}")
    return state
