"""
Scheduler module for OpenHarness HarnessFleet.
Implements affinity-aware scheduling, dependency-aware DAG execution, and adaptive sharding.
"""
from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Set
from openharness.fleet.models import (
    NodeState,
    TestAssignment,
    WorkerNode,
)


class Scheduler:
    """Intelligent test scheduler for the fleet.

    Supports:
    - Affinity-aware routing (tests with @requires go to matching nodes)
    - Dependency-aware DAG execution (@depends_on ordering)
    - Adaptive sharding (balanced split across healthy workers)
    """

    def __init__(self, workers: List[WorkerNode]):
        self.workers = workers

    def filter_capable_workers(
        self, requirements: Dict[str, Any]
    ) -> List[WorkerNode]:
        """Return healthy workers that satisfy the given capability requirements."""
        return [
            w
            for w in self.workers
            if w.state == NodeState.HEALTHY
            and w.capabilities.matches(requirements)
        ]

    def schedule_with_affinity(
        self,
        tests: List[Dict[str, Any]],
    ) -> List[TestAssignment]:
        """Schedule tests to workers based on capability requirements.

        Each test dict may contain a ``requires`` key mapping to a dict of
        capability requirements. Tests without requirements go to any
        healthy worker via round-robin.
        """
        assignments: List[TestAssignment] = []
        healthy = [w for w in self.workers if w.state == NodeState.HEALTHY]
        if not healthy:
            return assignments

        rr_counter = 0
        for test in tests:
            test_file = test.get("file", test.get("name", "unknown"))
            requires = test.get("requires", {})
            if requires:
                capable = self.filter_capable_workers(requires)
                if not capable:
                    continue
                worker = capable[rr_counter % len(capable)]
                rr_counter += 1
            else:
                worker = healthy[rr_counter % len(healthy)]
                rr_counter += 1
            assignments.append(
                TestAssignment(
                    test_file=test_file,
                    worker_id=worker.id,
                )
            )
        return assignments

    def topological_sort(
        self, tests: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """Order tests into parallel execution waves based on dependency graph.

        Returns a list of waves; each wave is a list of tests that can run
        concurrently (i.e. all their dependencies are in earlier waves).
        """
        test_map: Dict[str, Dict[str, Any]] = {}
        for t in tests:
            name = t.get("file", t.get("name", "unknown"))
            test_map[name] = t

        remaining: Set[str] = set(test_map.keys())
        completed: Set[str] = set()
        waves: List[List[Dict[str, Any]]] = []

        while remaining:
            wave: List[Dict[str, Any]] = []
            for name in sorted(remaining):
                t = test_map[name]
                deps = t.get("depends_on", [])
                if all(d in completed for d in deps):
                    wave.append(t)
            if not wave:
                wave = [test_map[n] for n in sorted(remaining)]
            for t in wave:
                name = t.get("file", t.get("name", "unknown"))
                remaining.discard(name)
                completed.add(name)
            waves.append(wave)
        return waves

    def shard_tests(
        self,
        test_files: List[str],
        num_shards: int,
        max_skew_pct: float = 20.0,
    ) -> List[List[str]]:
        """Split test files into balanced shards.

        Uses hash-based distribution for balance when no historical data is available.

        Args:
            test_files: Ordered list of test file paths.
            num_shards: Target number of shards (typically == healthy worker count).
            max_skew_pct: Maximum allowed wall-clock skew between shards.

        Returns:
            List of shards, each a list of test file paths.
        """
        if num_shards <= 0:
            return [test_files[:]] if test_files else []
        if not test_files:
            return [[] for _ in range(num_shards)]

        actual_shards = min(num_shards, len(test_files))
        buckets: List[List[str]] = [[] for _ in range(actual_shards)]
        bucket_weights: List[float] = [0.0] * actual_shards

        for f in test_files:
            min_idx = 0
            min_weight = bucket_weights[0]
            for i in range(1, actual_shards):
                if bucket_weights[i] < min_weight:
                    min_weight = bucket_weights[i]
                    min_idx = i
            buckets[min_idx].append(f)
            bucket_weights[min_idx] += self._estimate_weight(f)

        if len(buckets) > 1:
            self._rebalance(buckets, bucket_weights, max_skew_pct)

        return buckets

    def _estimate_weight(self, test_file: str) -> float:
        """Estimate relative runtime weight of a test file.

        Uses file name hash for deterministic pseudo-random weighting
        when no historical data is available.
        """
        h = hashlib.md5(test_file.encode()).hexdigest()
        return 1.0 + (int(h[:8], 16) % 100) / 100.0

    def _rebalance(
        self,
        buckets: List[List[str]],
        weights: List[float],
        max_skew_pct: float,
    ) -> None:
        """Move items from heaviest to lightest bucket until skew is acceptable."""
        if not buckets or len(buckets) < 2:
            return
        max_iterations = sum(len(b) for b in buckets) * 2
        for _ in range(max_iterations):
            total_weight = sum(weights)
            if total_weight == 0:
                break
            avg = total_weight / len(weights)
            heaviest = max(range(len(weights)), key=lambda i: weights[i])
            lightest = min(range(len(weights)), key=lambda i: weights[i])
            skew = (weights[heaviest] - avg) / avg * 100.0 if avg > 0 else 0.0
            if skew <= max_skew_pct:
                break
            if not buckets[heaviest]:
                break
            item = buckets[heaviest].pop()
            item_weight = self._estimate_weight(item)
            weights[heaviest] -= item_weight
            buckets[lightest].append(item)
            weights[lightest] += item_weight

    def create_shard_assignments(
        self,
        test_files: List[str],
        num_shards: int,
        max_skew_pct: float = 20.0,
    ) -> List[TestAssignment]:
        """Shard tests and assign each shard to a worker (round-robin)."""
        shards = self.shard_tests(test_files, num_shards, max_skew_pct)
        assignments: List[TestAssignment] = []
        healthy = [w for w in self.workers if w.state == NodeState.HEALTHY]
        if not healthy:
            return assignments
        for idx, shard in enumerate(shards):
            worker = healthy[idx % len(healthy)]
            for test_file in shard:
                assignments.append(
                    TestAssignment(
                        test_file=test_file,
                        worker_id=worker.id,
                        shard_index=idx,
                        shard_total=len(shards),
                    )
                )
        return assignments
