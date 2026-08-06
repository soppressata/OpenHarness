"""
Intelligent Scheduler ("The Conductor's Brain").
Handles affinity-aware scheduling, dependency DAG topological execution, adaptive sharding, and spot worker management.
"""

import math
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from .conductor import WorkerNode, NodeStatus


@dataclass
class TestSpec:
    __test__ = False
    test_id: str
    file_path: str
    name: str = ""
    requires: Dict[str, Any] = field(default_factory=dict)
    depends_on: List[str] = field(default_factory=list)
    estimated_duration: float = 1.0


@dataclass
class TestShard:
    shard_id: int
    test_specs: List[TestSpec] = field(default_factory=list)

    @property
    def total_estimated_duration(self) -> float:
        return sum(t.estimated_duration for t in self.test_specs)


class FleetScheduler:
    """
    Schedules test execution across available fleet workers with capability affinity,
    DAG topological sorting, and balanced sharding.
    """

    def __init__(self):
        pass

    def filter_nodes_by_affinity(self, test: TestSpec, nodes: List[WorkerNode]) -> List[WorkerNode]:
        """
        Filters candidate nodes based on test capability requirements (e.g. gpu, os, arch, browsers).
        """
        if not test.requires:
            return [n for n in nodes if n.status in (NodeStatus.HEALTHY, NodeStatus.BUSY)]

        eligible = []
        for node in nodes:
            if node.status not in (NodeStatus.HEALTHY, NodeStatus.BUSY):
                continue

            matches = True
            caps = node.capabilities

            for req_key, req_val in test.requires.items():
                if req_key == "gpu" or req_key == "gpus":
                    if req_val and caps.gpus <= 0:
                        matches = False
                        break
                elif req_key == "os":
                    if str(req_val).lower() != str(caps.os).lower():
                        matches = False
                        break
                elif req_key == "arch":
                    if str(req_val).lower() != str(caps.arch).lower():
                        matches = False
                        break
                elif req_key == "browser":
                    if req_val not in caps.browsers:
                        matches = False
                        break
                else:
                    if caps.custom.get(req_key) != req_val:
                        matches = False
                        break

            if matches:
                eligible.append(node)

        return eligible

    def build_dag_execution_order(self, tests: List[TestSpec]) -> List[List[TestSpec]]:
        """
        Builds parallel execution batches (topological levels) respecting test dependencies.
        Returns a list of test spec batches where each batch contains tests that can run concurrently.
        """
        spec_map = {t.test_id: t for t in tests}
        in_degree = {t.test_id: 0 for t in tests}
        dependents: Dict[str, List[str]] = {t.test_id: [] for t in tests}

        for t in tests:
            for dep in t.depends_on:
                if dep in spec_map:
                    dependents[dep].append(t.test_id)
                    in_degree[t.test_id] += 1

        levels: List[List[TestSpec]] = []

        while True:
            ready_ids = [tid for tid, deg in in_degree.items() if deg == 0]
            if not ready_ids:
                break

            current_level = [spec_map[tid] for tid in ready_ids]
            levels.append(current_level)

            for tid in ready_ids:
                del in_degree[tid]
                for child_id in dependents[tid]:
                    if child_id in in_degree:
                        in_degree[child_id] -= 1

        if in_degree:
            raise ValueError(f"Cyclic or unresolvable test dependencies detected in IDs: {list(in_degree.keys())}")

        return levels

    def split_into_shards(self, tests: List[TestSpec], num_shards: int) -> List[TestShard]:
        """
        Splits test specifications into balanced shards using LPT (Longest Processing Time first) heuristic
        to minimize wall-clock skew across shards.
        """
        if num_shards <= 0:
            num_shards = 1

        shards = [TestShard(shard_id=i) for i in range(num_shards)]
        sorted_tests = sorted(tests, key=lambda t: t.estimated_duration, reverse=True)

        for test in sorted_tests:
            min_shard = min(shards, key=lambda s: s.total_estimated_duration)
            min_shard.test_specs.append(test)

        return shards

    def calculate_shard_skew(self, shards: List[TestShard]) -> float:
        """
        Calculates wall-clock runtime skew percentage across shards.
        skew = (max_duration - mean_duration) / mean_duration
        """
        durations = [s.total_estimated_duration for s in shards]
        if not durations or sum(durations) == 0:
            return 0.0
        mean_dur = sum(durations) / len(durations)
        max_dur = max(durations)
        return (max_dur - mean_dur) / mean_dur if mean_dur > 0 else 0.0

    def schedule_execution_plan(
        self,
        tests: List[TestSpec],
        nodes: List[WorkerNode],
        shards_arg: str = "auto",
    ) -> Dict[str, List[TestSpec]]:
        """
        Schedules a full test suite onto available worker nodes, applying affinity filters,
        DAG ordering, and adaptive shard balancing.
        """
        healthy_nodes = [n for n in nodes if n.status in (NodeStatus.HEALTHY, NodeStatus.BUSY)]
        if not healthy_nodes:
            raise RuntimeError("No healthy worker nodes available for scheduling")

        num_nodes = len(healthy_nodes)
        if shards_arg == "auto":
            num_shards = num_nodes
        else:
            try:
                num_shards = int(shards_arg)
            except ValueError:
                num_shards = num_nodes

        assignments: Dict[str, List[TestSpec]] = {n.node_id: [] for n in healthy_nodes}

        dag_levels = self.build_dag_execution_order(tests)

        for level in dag_levels:
            for test in level:
                eligible = self.filter_nodes_by_affinity(test, healthy_nodes)
                if not eligible:
                    raise RuntimeError(f"No node matches required capabilities for test '{test.test_id}': {test.requires}")

                eligible_sorted = sorted(
                    eligible,
                    key=lambda n: (1 if n.ephemeral else 0, len(assignments[n.node_id]))
                )
                chosen_node = eligible_sorted[0]
                assignments[chosen_node.node_id].append(test)

        return assignments
