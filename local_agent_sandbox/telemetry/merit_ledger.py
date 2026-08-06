import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

DEFAULT_DB_PATH = os.path.join("telemetry", "merit.db")

MIGRATIONS: List[Tuple[int, str]] = [
    (
        1,
        """
        CREATE TABLE IF NOT EXISTS schema_version (
            version INTEGER PRIMARY KEY
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            category TEXT NOT NULL,
            persona TEXT NOT NULL,
            repo TEXT NOT NULL,
            detail TEXT,
            state TEXT
        );
        """,
    ),
]


class MeritLedger:
    """Local SQLite Merit Ledger recording loop events with forward-compatible migrations."""

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';"
            )
            if not cursor.fetchone():
                cursor.execute(
                    "CREATE TABLE schema_version (version INTEGER PRIMARY KEY);"
                )
                cursor.execute("INSERT INTO schema_version (version) VALUES (0);")
                conn.commit()

            cursor.execute("SELECT version FROM schema_version LIMIT 1;")
            row = cursor.fetchone()
            current_version = row[0] if row else 0

            for ver, sql in MIGRATIONS:
                if ver > current_version:
                    cursor.executescript(sql)
                    cursor.execute("UPDATE schema_version SET version = ?;", (ver,))
                    conn.commit()
                    current_version = ver

    def get_schema_version(self) -> int:
        """Get current schema version of the SQLite merit ledger."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT version FROM schema_version LIMIT 1;")
            row = cursor.fetchone()
            return row[0] if row else 0

    def record_event(
        self,
        category: str,
        persona: str,
        repo: str,
        detail: Any = None,
        state: Any = None,
    ) -> int:
        """Insert a loop event into the merit ledger."""
        timestamp = datetime.now(timezone.utc).isoformat()
        detail_str = (
            json.dumps(detail)
            if isinstance(detail, (dict, list))
            else (str(detail) if detail is not None else "")
        )
        state_str = (
            json.dumps(state)
            if isinstance(state, (dict, list))
            else (str(state) if state is not None else "")
        )

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO events (timestamp, category, persona, repo, detail, state)
                VALUES (?, ?, ?, ?, ?, ?);
                """,
                (timestamp, category, persona, repo, detail_str, state_str),
            )
            conn.commit()
            return cursor.lastrowid

    def get_events(
        self,
        category: Optional[str] = None,
        persona: Optional[str] = None,
        repo: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[dict]:
        """Query events from the merit ledger."""
        query = "SELECT id, timestamp, category, persona, repo, detail, state FROM events WHERE 1=1"
        params: List[Any] = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if persona:
            query += " AND persona = ?"
            params.append(persona)
        if repo:
            query += " AND repo = ?"
            params.append(repo)
        query += " ORDER BY id ASC"
        if limit:
            query += " LIMIT ?"
            params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]


from telemetry.merit_ledger import *
