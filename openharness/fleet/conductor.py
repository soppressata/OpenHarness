"""
Conductor module for OpenHarness HarnessFleet.
Implements the control plane: worker registry, heartbeat tracking, health monitoring, and quarantine logic.
"""
from __future__ import annotations

import threading
import time
from typing import Dict, List, Optional
from openharness.fleet.models import (
    FleetConfig,
    NodeState,
    WorkerCapabilities,
    WorkerNode,
    WorkerSpec,
)


class Conductor:
    """The Fleet Control Plane.

    Manages worker registration, heartbeat tracking, health monitoring,
    and automatic quarantine of unhealthy or flaky nodes.
    """

    def __init__(self, config: FleetConfig):
        self.config = config
        self.heartbeat_interval: float = config.conductor.get(
            "heartbeat_interval_sec", 5
        )
        self.miss_threshold: int = config.conductor.get(
            "heartbeat_miss_threshold", 3
        )
        self._workers: Dict[str, WorkerNode] = {}
        self._lock = threading.Lock()

    @property
    def worker_count(self) -> int:
        """Return total number of registered workers."""
        return len(self._workers)

    def register_worker(
        self,
        host: str,
        port: int,
        capabilities: Optional[WorkerCapabilities] = None,
        ephemeral: bool = False,
        labels: Optional[Dict[str, str]] = None,
        worker_id: Optional[str] = None,
    ) -> WorkerNode:
        """Register a new worker node with the conductor."""
        with self._lock:
            kwargs = {
                "host": host,
                "port": port,
                "capabilities": capabilities or WorkerCapabilities(),
                "ephemeral": ephemeral,
                "labels": labels or {},
            }
            if worker_id is not None:
                kwargs["id"] = worker_id
            node = WorkerNode(**kwargs)
            self._workers[node.id] = node
            return node

    def register_workers_from_config(self) -> List[WorkerNode]:
        """Register all worker specs defined in the fleet configuration."""
        nodes: List[WorkerNode] = []
        for spec in self.config.workers:
            node = self.register_worker(
                host=spec.host,
                port=spec.port,
                capabilities=spec.capabilities,
                ephemeral=spec.ephemeral,
                labels=spec.labels,
                worker_id=spec.id,
            )
            nodes.append(node)
        return nodes

    def heartbeat(self, worker_id: str) -> bool:
        """Record a heartbeat from a worker. Returns True if accepted."""
        with self._lock:
            node = self._workers.get(worker_id)
            if node is None:
                return False
            node.last_heartbeat = time.time()
            node.consecutive_missed = 0
            if node.state == NodeState.UNHEALTHY:
                node.state = NodeState.HEALTHY
            return True

    def record_infra_error(self, worker_id: str) -> None:
        """Record an infrastructure error for a worker; quarantine if threshold exceeded.

        A worker failing more than 5 infra errors within a 60-second window is auto-quarantined.
        """
        with self._lock:
            node = self._workers.get(worker_id)
            if node is None:
                return
            now = time.time()
            if now - node.infra_error_window_start > 60.0:
                node.infra_error_window_start = now
                node.infra_errors = 1
            else:
                node.infra_errors += 1
                if node.infra_errors > 5:
                    node.state = NodeState.QUARANTINED

    def check_health(self) -> Dict[str, NodeState]:
        """Evaluate health of all workers based on heartbeat freshness.

        Workers missing >= miss_threshold consecutive heartbeats are marked UNHEALTHY.
        Returns mapping of worker_id to current state.
        """
        now = time.time()
        with self._lock:
            for node in self._workers.values():
                elapsed = now - node.last_heartbeat
                if elapsed > self.heartbeat_interval:
                    missed_periods = int(elapsed / self.heartbeat_interval)
                    node.consecutive_missed = max(
                        node.consecutive_missed, missed_periods
                    )
                if (
                    node.state != NodeState.QUARANTINED
                    and node.consecutive_missed >= self.miss_threshold
                ):
                    node.state = NodeState.UNHEALTHY
            return {wid: node.state for wid, node in self._workers.items()}

    def get_healthy_workers(self) -> List[WorkerNode]:
        """Return all workers currently in HEALTHY state."""
        self.check_health()
        with self._lock:
            return [
                node
                for node in self._workers.values()
                if node.state == NodeState.HEALTHY
            ]

    def get_worker(self, worker_id: str) -> Optional[WorkerNode]:
        """Look up a worker by ID."""
        return self._workers.get(worker_id)

    def get_all_workers(self) -> List[WorkerNode]:
        """Return all registered workers."""
        return list(self._workers.values())

    def remove_worker(self, worker_id: str) -> bool:
        """Remove a worker from the registry. Returns True if found and removed."""
        with self._lock:
            if worker_id in self._workers:
                del self._workers[worker_id]
                return True
            return False

    def reset(self) -> None:
        """Clear all registered workers (for testing/restart)."""
        with self._lock:
            self._workers.clear()
