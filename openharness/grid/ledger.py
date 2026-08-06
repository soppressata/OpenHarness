"""
Harness Grid Observer Ledger ("The Witness").

An append-only, time-ordered, tamper-evident record of every executed shard and
its result across the mesh. Every record is chained to its predecessor through a
hash chain, so any retroactive edit is detected during verification. Record
identity is derived from ``(test_id, trace_id)``, which guarantees exactly-once
reporting even when a shard is re-executed on a healthy peer after a node failure.

This implements the Observer / Global Replay acceptance criterion (G9): any
historical result can be replayed byte-for-byte via ``harness grid replay``.
"""

import hashlib
import json
import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

GENESIS_HASH = "GENESIS"


def _canonical(payload: Dict[str, Any]) -> str:
    """Serializes a payload dict deterministically for hashing and byte-for-byte replay."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass
class GridResult:
    """A single shard execution outcome recorded in the grid ledger."""

    __test__ = False
    test_id: str
    node_id: str
    status: str
    error_message: str = ""
    stack_trace: str = ""
    duration_seconds: float = 0.0
    trace_id: str = ""
    artifacts: List[str] = field(default_factory=list)
    committed_at: float = field(default_factory=time.time)
    record_id: str = ""

    def __post_init__(self) -> None:
        if not self.record_id:
            self.record_id = f"{self.test_id}:{self.trace_id or uuid.uuid4().hex[:8]}"

    def content_payload(self) -> Dict[str, Any]:
        """Returns the canonical, order-stable payload dict for this record."""
        return {
            "record_id": self.record_id,
            "test_id": self.test_id,
            "node_id": self.node_id,
            "status": self.status,
            "error_message": self.error_message,
            "stack_trace": self.stack_trace,
            "duration_seconds": self.duration_seconds,
            "trace_id": self.trace_id,
            "artifacts": list(self.artifacts),
            "committed_at": self.committed_at,
        }

    def content_hash(self) -> str:
        """Returns the SHA-256 hash of this record's canonical payload."""
        return hashlib.sha256(_canonical(self.content_payload()).encode("utf-8")).hexdigest()

    def to_payload_json(self) -> str:
        """Returns the exact JSON string persisted for this record (byte-for-byte)."""
        return _canonical(self.content_payload())


class GridLedger:
    """
    Append-only, hash-chained ledger of grid execution results backed by SQLite.

    Each append seals the record against the previous record's hash, forming a
    chain that makes any modification detectable via :meth:`verify`. Duplicate
    appends of the same record (same ``test_id`` and ``trace_id``) are rejected,
    providing exactly-once semantics for re-dispatched shards.
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        parent = os.path.dirname(os.path.abspath(db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS grid_ledger (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                record_id TEXT NOT NULL UNIQUE,
                test_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                status TEXT NOT NULL,
                committed_at REAL NOT NULL,
                prev_hash TEXT NOT NULL DEFAULT '',
                record_hash TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_grid_ledger_test ON grid_ledger (test_id, committed_at)"
        )
        self._conn.commit()

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT record_hash FROM grid_ledger ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        return row[0] if row else GENESIS_HASH

    def append(self, result: GridResult) -> bool:
        """
        Appends a result to the ledger, chaining it to the previous record.

        Args:
            result: The execution outcome to record.

        Returns:
            ``True`` if the record was newly appended, ``False`` if a record with
            the same ``record_id`` already exists (exactly-once deduplication).
        """
        exists = self._conn.execute(
            "SELECT 1 FROM grid_ledger WHERE record_id = ?", (result.record_id,)
        ).fetchone()
        if exists:
            return False

        prev_hash = self._last_hash()
        record_hash = hashlib.sha256(
            (result.content_hash() + prev_hash).encode("utf-8")
        ).hexdigest()
        payload_json = result.to_payload_json()

        self._conn.execute(
            """
            INSERT INTO grid_ledger
                (record_id, test_id, node_id, status, committed_at, prev_hash, record_hash, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.record_id,
                result.test_id,
                result.node_id,
                result.status,
                result.committed_at,
                prev_hash,
                record_hash,
                payload_json,
            ),
        )
        self._conn.commit()
        return True

    def replay_payload(self, test_id: str, timestamp: float) -> Optional[str]:
        """
        Returns the exact persisted payload JSON for ``test_id`` committed at or
        before ``timestamp`` (byte-for-byte), or ``None`` when no such record exists.

        Args:
            test_id: The test identifier to look up.
            timestamp: Upper bound on the commit time (epoch seconds).
        """
        row = self._conn.execute(
            """
            SELECT payload_json FROM grid_ledger
            WHERE test_id = ? AND committed_at <= ?
            ORDER BY committed_at DESC, seq DESC LIMIT 1
            """,
            (test_id, timestamp),
        ).fetchone()
        return row[0] if row else None

    def replay(self, test_id: str, timestamp: float) -> Optional[GridResult]:
        """
        Replays the most recent ``GridResult`` for ``test_id`` committed at or
        before ``timestamp``. The reconstructed record carries a payload that is
        byte-for-byte identical to what was originally recorded.

        Args:
            test_id: The test identifier to look up.
            timestamp: Upper bound on the commit time (epoch seconds).
        """
        payload = self.replay_payload(test_id, timestamp)
        if payload is None:
            return None
        return GridResult(**json.loads(payload))

    def latest(self, test_id: str) -> Optional[GridResult]:
        """
        Returns the most recently committed result for ``test_id``, or ``None``
        if the ledger has no record for it.
        """
        row = self._conn.execute(
            """
            SELECT payload_json FROM grid_ledger
            WHERE test_id = ?
            ORDER BY committed_at DESC, seq DESC LIMIT 1
            """,
            (test_id,),
        ).fetchone()
        if row is None:
            return None
        return GridResult(**json.loads(row[0]))

    def count(self) -> int:
        """Returns the number of records currently in the ledger."""
        return self._conn.execute("SELECT COUNT(*) FROM grid_ledger").fetchone()[0]

    def verify(self) -> List[str]:
        """
        Walks the hash chain and reports every integrity violation.

        Returns:
            A list of human-readable violations; an empty list means the ledger
            is intact (no record was altered or reordered out of the chain).
        """
        violations: List[str] = []
        rows = self._conn.execute(
            "SELECT record_id, prev_hash, record_hash, payload_json FROM grid_ledger ORDER BY seq ASC"
        ).fetchall()
        expected_prev = GENESIS_HASH
        for record_id, prev_hash, record_hash, payload_json in rows:
            content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            recomputed = hashlib.sha256(
                (content_hash + prev_hash).encode("utf-8")
            ).hexdigest()
            if recomputed != record_hash:
                violations.append(f"record {record_id}: record_hash mismatch (tampered payload)")
            if prev_hash != expected_prev:
                violations.append(f"record {record_id}: chain broken (prev_hash mismatch)")
            expected_prev = record_hash
        return violations

    def close(self) -> None:
        """Closes the underlying SQLite connection."""
        self._conn.close()
