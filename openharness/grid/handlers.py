"""
Harness Grid CLI Handlers.

Implements the ``harness grid {init,join,leave,status,watch,replay}`` subcommand
handlers: mesh bootstrap, node onboarding, self-healing decommission with
in-flight re-dispatch, live health watch, and the Observer / Global Replay ledger.
"""

import time
from typing import Any, Dict, List, Optional

from ..fleet import (
    FleetConductor,
    NodeStatus,
    WorkerNode,
    handle_fleet_init,
    handle_fleet_join,
    handle_fleet_status,
    load_config,
)
from .ledger import GridLedger

DEFAULT_LEDGER_PATH = ".openharness/grid/ledger.db"


def handle_grid_init(cluster_name: str = "harness-grid-primary", output_path: str = "fleet.yaml") -> str:
    """
    Initializes a grid fleet configuration file (mesh bootstrap).

    Args:
        cluster_name: Name of the grid cluster.
        output_path: Where the fleet.yaml configuration is written.

    Returns:
        The absolute path of the written configuration file.
    """
    saved_path = handle_fleet_init(cluster_name=cluster_name, output_path=output_path)
    print(f"[HarnessGrid] Initialized grid cluster config at '{saved_path}'")
    return saved_path


def handle_grid_join(conductor_address: str = "127.0.0.1:9443", token: Optional[str] = None) -> WorkerNode:
    """
    Joins the current host to an existing grid mesh as a worker node.

    Args:
        conductor_address: Address of the grid control plane to enroll with.
        token: Short-lived worker enrollment token.

    Returns:
        The registered ``WorkerNode``.
    """
    node = handle_fleet_join(conductor_address=conductor_address, token=token)
    print(f"[HarnessGrid] Node '{node.node_id}' joined the grid at {conductor_address}")
    return node


def handle_grid_status(config_path: str = "fleet.yaml") -> str:
    """
    Renders the current grid node health table.

    Args:
        config_path: Path to the grid fleet.yaml configuration.

    Returns:
        The rendered status table as a string.
    """
    config = load_config(config_path)
    return handle_fleet_status(conductor=FleetConductor(config=config))


def handle_grid_leave(
    node_id: str,
    in_flight: Optional[List[str]] = None,
    config_path: str = "fleet.yaml",
    conductor: Optional[FleetConductor] = None,
) -> Dict[str, Any]:
    """
    Decommissions a node from the grid (self-healing topology).

    The node is cordoned (marked ``DRAINING``) and its in-flight shard IDs are
    re-dispatched round-robin to healthy peers. If no healthy peers exist the
    shards are returned as ``undispatched`` so the caller can retry later.

    Args:
        node_id: Identifier of the node leaving the grid.
        in_flight: Optional list of in-flight shard IDs to re-dispatch.
        config_path: Path to the grid fleet.yaml configuration.
        conductor: Optional pre-built conductor (used by tests and embedded calls).

    Returns:
        A drain report with the leaving node, its status, and the re-dispatch map.

    Raises:
        ValueError: If ``node_id`` is not a member of the grid.
    """
    cond = conductor or FleetConductor(config=load_config(config_path))
    node = cond.nodes.get(node_id)
    if node is None:
        raise ValueError(f"Unknown grid node: {node_id}")

    node.status = NodeStatus.DRAINING

    healthy = [n for n in cond.get_healthy_nodes() if n.node_id != node_id]
    redispatched: Dict[str, List[str]] = {}
    undispatched: List[str] = []

    for idx, shard in enumerate(in_flight or []):
        if healthy:
            target = healthy[idx % len(healthy)]
            redispatched.setdefault(target.node_id, []).append(shard)
        else:
            undispatched.append(shard)

    report = {
        "left_node": node_id,
        "status": "DRAINED",
        "drained_at": time.time(),
        "in_flight_shards": list(in_flight or []),
        "redispatched": redispatched,
        "undispatched": undispatched,
    }
    print(
        f"[HarnessGrid] Node '{node_id}' drained; redispatched "
        f"{sum(len(v) for v in redispatched.values())} shard(s), "
        f"{len(undispatched)} left undispatched."
    )
    return report


def handle_grid_watch(
    iterations: int = 1,
    interval: float = 1.0,
    config_path: str = "fleet.yaml",
    nodes_count: int = 3,
    conductor: Optional[FleetConductor] = None,
) -> Dict[str, Any]:
    """
    Watches grid health across heartbeat windows (self-healing convergence).

    Samples node health once per iteration; a node that stops heartbeating is
    flagged ``UNHEALTHY`` within the configured heartbeat window, and a fresh
    heartbeat restores it to ``HEALTHY``. Convergence means zero unhealthy nodes.

    Args:
        iterations: Number of health samples to take.
        interval: Seconds to wait between samples.
        config_path: Path to the grid fleet.yaml configuration.
        nodes_count: Demo nodes to register when the registry is empty.
        conductor: Optional pre-built conductor (used by tests and embedded calls).

    Returns:
        A report with the final health snapshot and a ``converged`` flag.
    """
    cond = conductor or FleetConductor(config=load_config(config_path))
    if not cond.nodes:
        for i in range(nodes_count):
            cond.register_node(f"127.0.0.1:{9444 + i}", hostname=f"node-{i + 1}")

    snapshots: List[Dict[str, Any]] = []
    for iteration in range(max(1, iterations)):
        unhealthy = cond.check_heartbeats()
        summary = cond.get_grid_summary()
        summary["unhealthy_ids"] = unhealthy
        snapshots.append(summary)
        print(
            f"[HarnessGrid] watch[{iteration + 1}/{iterations}] nodes={summary['total']} "
            f"healthy={summary['healthy']} unhealthy={summary['unhealthy']} quarantined={summary['quarantined']}"
        )
        if iteration < iterations - 1 and interval > 0:
            time.sleep(interval)

    final_snapshot = snapshots[-1]
    converged = final_snapshot["unhealthy"] == 0
    print(f"[HarnessGrid] Health {'converged' if converged else 'not converged'}.")
    return {"converged": converged, "snapshots": snapshots, "final": final_snapshot}


def handle_grid_replay(
    spec: str,
    ledger_path: str = DEFAULT_LEDGER_PATH,
) -> Dict[str, Any]:
    """
    Replays a historical grid result byte-for-byte (Observer / Global Replay).

    Args:
        spec: Replay spec in the form ``<test_id>@<timestamp>``.
        ledger_path: Path to the grid observer ledger database.

    Returns:
        A dict with the parsed ``test_id``, ``timestamp``, and the exact
        ``payload_json`` that was originally recorded for that moment in time.

    Raises:
        ValueError: If ``spec`` is malformed (missing ``@`` or bad timestamp).
        LookupError: If no record exists for the test at or before the timestamp.
    """
    test_id, separator, timestamp_str = spec.partition("@")
    if not test_id or not separator or not timestamp_str:
        raise ValueError("replay spec must be '<test_id>@<timestamp>'")
    try:
        timestamp = float(timestamp_str)
    except ValueError:
        raise ValueError(f"invalid timestamp: {timestamp_str!r}")

    ledger = GridLedger(ledger_path)
    try:
        payload = ledger.replay_payload(test_id, timestamp)
    finally:
        ledger.close()
    if payload is None:
        raise LookupError(
            f"No grid result for test '{test_id}' at or before {timestamp}"
        )

    print(payload)
    return {"test_id": test_id, "timestamp": timestamp, "payload_json": payload}
