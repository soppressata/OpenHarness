"""
Self-Healing Workers & Result Reconciliation Engine ("The Immune System").
Distinguishes infrastructure errors (retried with backoff) vs assertion failures (never retried),
quarantines faulty nodes exceeding error thresholds, and reconciles checksummed test results.
"""

import time
import hashlib
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from .conductor import FleetConductor


class ErrorType(str, Enum):
    INFRASTRUCTURE = "INFRASTRUCTURE"
    ASSERTION = "ASSERTION"
    UNKNOWN = "UNKNOWN"


@dataclass
class TestExecutionResult:
    __test__ = False
    test_id: str
    node_id: str
    status: str
    error_message: str = ""
    stack_trace: str = ""
    duration_seconds: float = 0.0
    trace_id: str = ""
    timestamp: float = field(default_factory=time.time)
    artifacts: List[str] = field(default_factory=list)
    checksum: str = ""

    def __post_init__(self):
        if not self.checksum:
            self.checksum = self.compute_checksum()

    def compute_checksum(self) -> str:
        raw = f"{self.test_id}:{self.status}:{self.error_message}:{self.duration_seconds}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class FleetSelfHealingEngine:
    """
    Evaluates test failures, applies self-healing rules (retry infra vs assert fail),
    manages worker quarantine windows, and reconciles deduplicated test execution results.
    """

    def __init__(
        self,
        conductor: FleetConductor,
        max_infra_retries: int = 3,
        quarantine_threshold: int = 5,
        quarantine_window_seconds: int = 60,
    ):
        self.conductor = conductor
        self.max_infra_retries = max_infra_retries
        self.quarantine_threshold = quarantine_threshold
        self.quarantine_window_seconds = quarantine_window_seconds
        self.retry_counts: Dict[str, int] = {}
        self.reconciled_results: Dict[str, TestExecutionResult] = {}

    def classify_error(self, error_message: str, stack_trace: str = "") -> ErrorType:
        """
        Classifies errors into INFRASTRUCTURE (retriable) vs ASSERTION (non-retriable).
        Assertion failures, AssertionError, and explicit test failure assertions are NEVER retried.
        """
        combined = f"{error_message}\n{stack_trace}".lower()

        if "assertionerror" in combined or "assert " in combined or "failed assertion" in combined:
            return ErrorType.ASSERTION

        infra_signatures = [
            "connection refused", "timeout", "worker crashed", "node offline",
            "socket error", "broken pipe", "oom", "out of memory", "runner exited",
            "systemerror", "oserror", "process terminated", "infrastructure"
        ]

        for sig in infra_signatures:
            if sig in combined:
                return ErrorType.INFRASTRUCTURE

        if "error" in combined and "assert" not in combined:
            return ErrorType.INFRASTRUCTURE

        return ErrorType.ASSERTION

    def record_node_infra_error(self, node_id: str, timestamp: Optional[float] = None) -> bool:
        """
        Records an infrastructure error for a worker node.
        If node exceeds quarantine_threshold within quarantine_window_seconds, auto-quarantines the node.
        Returns True if node was newly quarantined.
        """
        node = self.conductor.nodes.get(node_id)
        if not node:
            return False

        ts = timestamp if timestamp is not None else time.time()
        node.infra_error_timestamps.append(ts)

        cutoff = ts - self.quarantine_window_seconds
        node.infra_error_timestamps = [t for t in node.infra_error_timestamps if t >= cutoff]

        # The policy is "more than five" errors, so the threshold is crossed
        # by the first error strictly above the configured value.
        if len(node.infra_error_timestamps) > self.quarantine_threshold:
            self.conductor.quarantine_node(
                node_id,
                reason=f"Exceeded {self.quarantine_threshold} infrastructure errors in {self.quarantine_window_seconds}s window"
            )
            return True

        return False

    def handle_test_failure(
        self,
        test_id: str,
        node_id: str,
        error_message: str,
        stack_trace: str = "",
        duration: float = 0.0,
        trace_id: str = "",
    ) -> Tuple[bool, Optional[str]]:
        """
        Processes a test execution failure.
        Returns Tuple[should_retry: bool, new_assigned_node_id: Optional[str]].
        Rule: Assertion failures are NEVER retried. Infrastructure errors ARE retried up to max_infra_retries.
        """
        err_type = self.classify_error(error_message, stack_trace)

        if err_type == ErrorType.INFRASTRUCTURE:
            self.record_node_infra_error(node_id)
            current_retries = self.retry_counts.get(test_id, 0)
            if current_retries < self.max_infra_retries:
                self.retry_counts[test_id] = current_retries + 1
                healthy_nodes = [
                    n for n in self.conductor.get_healthy_nodes() if n.node_id != node_id
                ]
                new_node = healthy_nodes[0].node_id if healthy_nodes else node_id
                return True, new_node

        return False, None

    def reconcile_result(self, result: TestExecutionResult) -> bool:
        """
        Deduplicates and stores test result using checksum verification.
        Returns True if result was newly reconciled, False if duplicate.
        """
        existing = self.reconciled_results.get(result.test_id)
        if existing and existing.checksum == result.checksum:
            return False

        self.reconciled_results[result.test_id] = result
        return True

    def get_summary(self) -> Dict[str, Any]:
        """Returns statistics on test retries and reconciled results."""
        passed = len([r for r in self.reconciled_results.values() if r.status == "PASSED"])
        failed = len([r for r in self.reconciled_results.values() if r.status == "FAILED"])
        infra_errs = len([r for r in self.reconciled_results.values() if r.status == "INFRA_ERROR"])
        return {
            "total_reconciled": len(self.reconciled_results),
            "passed": passed,
            "failed": failed,
            "infra_errors": infra_errs,
            "total_retries_attempted": sum(self.retry_counts.values()),
        }
