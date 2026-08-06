"""
Failure classification and retry logic for OpenHarness HarnessFleet.
Distinguishes infrastructure errors from assertion failures and applies
appropriate retry strategies with exponential backoff.
"""
from __future__ import annotations

import enum
import time
from typing import Tuple


class FailureType(str, enum.Enum):
    """Classification of test failure types."""

    INFRA = "INFRA"
    ASSERTION = "ASSERTION"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


_INFRA_INDICATORS = (
    "connection refused",
    "connection reset",
    "no such file",
    "cannot connect",
    "network is unreachable",
    "name or service not known",
    "temporary failure",
    "service unavailable",
    "connectionerror",
    "timeouterror",
    "nodename nor servname",
    "address already in use",
    "broken pipe",
    "connection aborted",
    "errno 111",
    "errno 104",
)


def classify_failure(
    error_message: str, return_code: int, timed_out: bool = False
) -> FailureType:
    """Classify a test failure based on error output and context.

    Args:
        error_message: The error output from the test process.
        return_code: The process return code.
        timed_out: Whether the test timed out.

    Returns:
        The failure type classification.
    """
    if timed_out:
        return FailureType.TIMEOUT

    error_lower = error_message.lower()

    for indicator in _INFRA_INDICATORS:
        if indicator in error_lower:
            return FailureType.INFRA

    if return_code != 0:
        return FailureType.ASSERTION

    return FailureType.UNKNOWN


def should_retry(
    failure_type: FailureType, attempt: int, max_retries: int = 2
) -> bool:
    """Determine if a failure should be retried.

    Infrastructure errors and timeouts are retried up to max_retries.
    Assertion failures are never retried (deterministic).

    Args:
        failure_type: The type of failure.
        attempt: Current attempt number (0-indexed).
        max_retries: Maximum number of retry attempts.

    Returns:
        True if the test should be retried.
    """
    if failure_type == FailureType.ASSERTION:
        return False
    if attempt >= max_retries:
        return False
    return True


def backoff_delay(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> float:
    """Calculate exponential backoff delay.

    Args:
        attempt: Current attempt number (0-indexed).
        base_delay: Base delay in seconds.
        max_delay: Maximum delay cap.

    Returns:
        Delay in seconds.
    """
    delay = base_delay * (2 ** attempt)
    return min(delay, max_delay)
