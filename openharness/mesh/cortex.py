"""
Self-Healing Reliability Engine ("The Cortex").

Statistical flake detection, auto-quarantine/promotion, predictive re-ordering,
and signed decision records.
"""
from __future__ import annotations

import math
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Deque, Dict, List, Optional, Sequence

from pydantic import BaseModel, Field

from openharness.mesh.events import EventType, make_event
from openharness.mesh.identity import PeerIdentity, Attestation


class TestRunOutcome(BaseModel):
    """Single observed outcome of a test execution."""

    __test__ = False

    test_id: str
    passed: bool
    branch: str = "main"
    environment: str = "default"
    duration_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    error_fingerprint: str = ""


class QuarantineDecision(BaseModel):
    """Auditable quarantine or promotion decision (AC-12)."""

    decision_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    test_id: str
    action: str  # quarantine | promote | observe
    confidence: float
    reason: str
    model_stats: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    attestation: Optional[Dict[str, Any]] = None
    event_id: str = ""

    def to_audit_record(self) -> Dict[str, Any]:
        return self.model_dump()


class _TestStats:
    """Running Bayesian-ish pass-rate model for one test key."""

    def __init__(self, window: int = 50):
        self.window = window
        self.outcomes: Deque[bool] = deque(maxlen=window)
        self.quarantined: bool = False
        self.clean_since_quarantine: int = 0
        self.total_runs: int = 0
        self.pass_count: int = 0
        self.fail_count: int = 0
        self.inconsistent_streak: int = 0
        self._last_passed: Optional[bool] = None

    def observe(self, passed: bool) -> None:
        self.outcomes.append(passed)
        self.total_runs += 1
        if passed:
            self.pass_count += 1
            if self.quarantined:
                self.clean_since_quarantine += 1
        else:
            self.fail_count += 1
            self.clean_since_quarantine = 0

        if self._last_passed is not None and self._last_passed != passed:
            self.inconsistent_streak += 1
        else:
            # reset only when we get a stable streak after flip counting period
            if self._last_passed is not None and self._last_passed == passed:
                pass
        # Count consecutive flips within recent window
        self.inconsistent_streak = self._count_recent_flips()
        self._last_passed = passed

    def _count_recent_flips(self) -> int:
        if len(self.outcomes) < 2:
            return 0
        flips = 0
        prev = self.outcomes[0]
        for o in list(self.outcomes)[1:]:
            if o != prev:
                flips += 1
            prev = o
        return flips

    def pass_rate(self) -> float:
        if not self.outcomes:
            return 1.0
        return sum(1 for o in self.outcomes if o) / len(self.outcomes)

    def flake_probability(self) -> float:
        """Beta-Binomial style flake score in [0, 1].

        High when outcomes oscillate and pass rate is mid-range.
        """
        n = len(self.outcomes)
        if n < 2:
            return 0.0
        # Prior Beta(1,1); posterior mean of "flip rate"
        flips = self._count_recent_flips()
        # max flips in n trials is n-1
        flip_rate = flips / max(1, n - 1)
        rate = self.pass_rate()
        # Peak ambiguity near 0.5 pass rate
        ambiguity = 1.0 - abs(2.0 * rate - 1.0)
        return max(0.0, min(1.0, 0.6 * flip_rate + 0.4 * ambiguity * flip_rate))

    def consecutive_inconsistent_runs(self) -> int:
        """Length of trailing window that still shows inconsistency."""
        outs = list(self.outcomes)
        if len(outs) < 2:
            return 0
        # Walk back while we keep seeing both pass and fail in the trailing segment
        for size in range(len(outs), 1, -1):
            window = outs[-size:]
            if any(window) and not all(window):
                # count how many transitions in this window as "inconsistent runs"
                return size
        return 0


def _test_key(test_id: str, branch: str, environment: str) -> str:
    return f"{test_id}|{branch}|{environment}"


class CortexEngine:
    """Statistical flake model with quarantine, promotion, and predictive reorder."""

    def __init__(
        self,
        identity: Optional[PeerIdentity] = None,
        quarantine_inconsistent_runs: int = 5,
        promotion_clean_runs: int = 10,
        flake_confidence_threshold: float = 0.55,
    ):
        self.identity = identity or PeerIdentity.generate(cluster_id="cortex")
        self.quarantine_inconsistent_runs = quarantine_inconsistent_runs
        self.promotion_clean_runs = promotion_clean_runs
        self.flake_confidence_threshold = flake_confidence_threshold
        self._stats: Dict[str, _TestStats] = {}
        self.decisions: List[QuarantineDecision] = []
        self.event_log: List[Dict[str, Any]] = []

    def _get_stats(self, outcome: TestRunOutcome) -> _TestStats:
        key = _test_key(outcome.test_id, outcome.branch, outcome.environment)
        if key not in self._stats:
            self._stats[key] = _TestStats()
        return self._stats[key]

    def record(self, outcome: TestRunOutcome) -> Optional[QuarantineDecision]:
        """Ingest a run outcome; may emit quarantine/promotion decision (AC-9/10/12)."""
        stats = self._get_stats(outcome)
        stats.observe(outcome.passed)
        decision: Optional[QuarantineDecision] = None

        conf = stats.flake_probability()
        inconsistent = stats.consecutive_inconsistent_runs()

        if (
            not stats.quarantined
            and inconsistent >= self.quarantine_inconsistent_runs
            and conf >= self.flake_confidence_threshold
        ):
            stats.quarantined = True
            # N clean runs required after the quarantine decision (AC-10).
            stats.clean_since_quarantine = 0
            decision = self._decide(
                outcome.test_id,
                "quarantine",
                confidence=conf,
                reason=(
                    f"auto-quarantine after {inconsistent} inconsistent runs "
                    f"(flake_probability={conf:.3f})"
                ),
                stats=stats,
            )
        elif stats.quarantined and stats.clean_since_quarantine >= self.promotion_clean_runs:
            stats.quarantined = False
            decision = self._decide(
                outcome.test_id,
                "promote",
                confidence=1.0 - conf,
                reason=(
                    f"auto-promote after {stats.clean_since_quarantine} clean runs "
                    f"(N={self.promotion_clean_runs})"
                ),
                stats=stats,
            )

        return decision

    def _decide(
        self,
        test_id: str,
        action: str,
        confidence: float,
        reason: str,
        stats: _TestStats,
    ) -> QuarantineDecision:
        att: Optional[Attestation] = self.identity.attest(
            action=f"cortex.{action}",
            subject=test_id,
            metadata={"confidence": confidence},
        )
        event = make_event(
            EventType.QUARANTINE if action == "quarantine" else EventType.PROMOTION,
            self.identity,
            payload={"test_id": test_id, "action": action, "confidence": confidence, "reason": reason},
        )
        decision = QuarantineDecision(
            test_id=test_id,
            action=action,
            confidence=confidence,
            reason=reason,
            model_stats={
                "pass_rate": stats.pass_rate(),
                "total_runs": stats.total_runs,
                "flake_probability": stats.flake_probability(),
                "clean_since_quarantine": stats.clean_since_quarantine,
                "quarantined": stats.quarantined,
            },
            attestation=att.model_dump() if att else None,
            event_id=event.event_id,
        )
        self.decisions.append(decision)
        self.event_log.append(event.to_audit_record())
        return decision

    def is_quarantined(self, test_id: str, branch: str = "main", environment: str = "default") -> bool:
        key = _test_key(test_id, branch, environment)
        stats = self._stats.get(key)
        return bool(stats and stats.quarantined)

    def get_confidence(self, test_id: str, branch: str = "main", environment: str = "default") -> float:
        key = _test_key(test_id, branch, environment)
        stats = self._stats.get(key)
        return stats.flake_probability() if stats else 0.0

    def predictive_reorder(self, tests: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Reorder suites to surface failures earliest (AC-11).

        Higher failure likelihood and historically failing tests run first.
        Each test dict needs ``id`` or ``name``; optional ``priority`` boost.
        """
        def fail_likelihood(t: Dict[str, Any]) -> float:
            tid = str(t.get("id", t.get("name", "")))
            branch = str(t.get("branch", "main"))
            env = str(t.get("environment", "default"))
            key = _test_key(tid, branch, env)
            stats = self._stats.get(key)
            base = 0.5
            if stats and stats.outcomes:
                base = 1.0 - stats.pass_rate()
                base = max(base, stats.flake_probability())
            # explicit hint from caller
            if "fail_likelihood" in t:
                base = max(base, float(t["fail_likelihood"]))
            priority = float(t.get("priority", 0.0))
            return base + priority * 0.01

        return sorted(list(tests), key=fail_likelihood, reverse=True)

    def median_first_failure_time(
        self,
        ordered_tests: Sequence[Dict[str, Any]],
        durations_key: str = "duration_ms",
    ) -> Optional[float]:
        """Compute time-to-first-failure for an ordered list (benchmark helper)."""
        elapsed = 0.0
        found = False
        for t in ordered_tests:
            elapsed += float(t.get(durations_key, 0.0))
            tid = str(t.get("id", t.get("name", "")))
            if t.get("will_fail") or t.get("fail"):
                found = True
                break
            key = _test_key(tid, str(t.get("branch", "main")), str(t.get("environment", "default")))
            stats = self._stats.get(key)
            if stats and stats.outcomes and stats.pass_rate() < 0.5:
                found = True
                break
        return elapsed if found else None
