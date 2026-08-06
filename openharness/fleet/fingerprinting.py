"""
Failure fingerprinting for OpenHarness HarnessFleet.
Clusters failures by signature to identify flaky patterns and common root causes.
"""
from __future__ import annotations

import hashlib
import re
from typing import Dict, List, Tuple


def compute_fingerprint(error_message: str) -> str:
    """Compute a stable fingerprint for a failure.

    Normalizes the error message by removing variable parts (timestamps,
    PIDs, memory addresses, line numbers) and hashes the result.

    Args:
        error_message: The raw error output from a test.

    Returns:
        A 16-character hex fingerprint string.
    """
    normalized = error_message

    normalized = re.sub(r"0x[0-9a-fA-F]+", "0xADDR", normalized)
    normalized = re.sub(
        r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})?",
        "TIMESTAMP",
        normalized,
    )
    normalized = re.sub(r"\bpid\s*\d+\b", "pid PID", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"line \d+", "line N", normalized)
    normalized = re.sub(r"\b\d+\b", "N", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()

    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def cluster_failures(failures: List[Tuple[str, str]]) -> Dict[str, List[str]]:
    """Cluster failed tests by their error fingerprint.

    Args:
        failures: List of (test_file, error_message) tuples.

    Returns:
        Dict mapping fingerprint to list of test files sharing that signature.
    """
    clusters: Dict[str, List[str]] = {}
    for test_file, error_message in failures:
        fp = compute_fingerprint(error_message)
        if fp not in clusters:
            clusters[fp] = []
        clusters[fp].append(test_file)
    return clusters


def find_flaky_clusters(
    clusters: Dict[str, List[str]], threshold: int = 2
) -> Dict[str, List[str]]:
    """Identify clusters that indicate flaky behavior.

    A cluster is considered flaky if it contains multiple tests with
    the same failure signature.

    Args:
        clusters: Output from cluster_failures.
        threshold: Minimum number of tests to consider a cluster flaky.

    Returns:
        Filtered dict with only flaky clusters.
    """
    return {
        fp: tests for fp, tests in clusters.items() if len(tests) >= threshold
    }
