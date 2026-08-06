"""
Storage module for OpenHarness.
Provides core functionality for the storage subsystem.
"""
import json
import os
import sqlite3
import time
import contextlib
import abc
from typing import Any, Dict, List, Optional
from openharness.core.types import EvaluationResult, MetricScore, Trajectory, Step, ToolCall


class StorageEngine(metaclass=abc.ABCMeta):
    """Base storage engine / Factory for OpenHarness storage backends."""
    
    def __new__(cls, db_path: str = ".openharness/evals.db"):
        db_url = os.environ.get("OPENHARNESS_DB_URL")
        if db_url and (db_url.startswith("postgresql://") or db_url.startswith("postgres://")):
            return PostgresStorage(db_url)
        return SQLiteStorage(db_path)

    @abc.abstractmethod
    def save_run(self, run_id: str, name: str, results: List[EvaluationResult], metadata: Optional[Dict[str, Any]] = None):
        pass

    @abc.abstractmethod
    def get_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        pass

    @abc.abstractmethod
    def delete_run(self, run_id: str):
        pass


class SQLiteStorage:
    """Embedded SQLite storage engine with WAL mode and busy_timeout."""

    def __init__(self, db_path: str = ".openharness/evals.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    @contextlib.contextmanager
    def _connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            yield conn
        finally:
            conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        # Exposing for backward compatibility where storage._get_connection() is used
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        return conn

    def _init_db(self):
        with self._connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        passed_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        total_count INTEGER DEFAULT 0,
                        duration_ms REAL DEFAULT 0.0,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evaluation_results (
                        id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        test_case_name TEXT NOT NULL,
                        passed INTEGER NOT NULL,
                        total_score REAL NOT NULL,
                        duration_ms REAL NOT NULL,
                        timestamp REAL NOT NULL,
                        trajectory_id TEXT,
                        metadata TEXT,
                        FOREIGN KEY (run_id) REFERENCES runs(id)
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trajectories (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        input_prompt TEXT,
                        final_output TEXT,
                        total_duration_ms REAL,
                        total_prompt_tokens INTEGER,
                        total_completion_tokens INTEGER,
                        steps_json TEXT,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS metric_scores (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        evaluation_result_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        score REAL NOT NULL,
                        passed INTEGER NOT NULL,
                        reason TEXT,
                        category TEXT,
                        metadata TEXT,
                        FOREIGN KEY (evaluation_result_id) REFERENCES evaluation_results(id)
                    )
                """)

    def save_run(self, run_id: str, name: str, results: List[EvaluationResult], metadata: Optional[Dict[str, Any]] = None):
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        total_duration = sum(r.duration_ms for r in results)
        
        with self._connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO runs (id, name, timestamp, passed_count, failed_count, total_count, duration_ms, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    run_id,
                    name,
                    time.time(),
                    passed_count,
                    failed_count,
                    len(results),
                    total_duration,
                    json.dumps(metadata or {})
                ))

                for result in results:
                    traj_id = None
                    if result.trajectory:
                        traj_id = result.trajectory.id
                        cursor.execute("""
                            INSERT OR REPLACE INTO trajectories 
                            (id, name, input_prompt, final_output, total_duration_ms, total_prompt_tokens, total_completion_tokens, steps_json, metadata)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            result.trajectory.id,
                            result.trajectory.name,
                            result.trajectory.input_prompt,
                            result.trajectory.final_output,
                            result.trajectory.total_duration_ms,
                            result.trajectory.total_prompt_tokens,
                            result.trajectory.total_completion_tokens,
                            json.dumps([s.model_dump() for s in result.trajectory.steps]),
                            json.dumps(result.trajectory.metadata)
                        ))

                    cursor.execute("""
                        INSERT OR REPLACE INTO evaluation_results
                        (id, run_id, test_case_name, passed, total_score, duration_ms, timestamp, trajectory_id, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        result.id,
                        run_id,
                        result.test_case_name,
                        1 if result.passed else 0,
                        result.total_score,
                        result.duration_ms,
                        result.timestamp,
                        traj_id,
                        json.dumps(result.metadata)
                    ))

                    for m in result.metrics:
                        cursor.execute("""
                            INSERT INTO metric_scores (evaluation_result_id, name, score, passed, reason, category, metadata)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            result.id,
                            m.name,
                            m.score,
                            1 if m.passed else 0,
                            m.reason,
                            m.category,
                            json.dumps(m.metadata)
                        ))

    def get_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM runs ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cursor.fetchall()
            runs = []
            for r in rows:
                r_dict = dict(r)
                if isinstance(r_dict.get("metadata"), str):
                    r_dict["metadata"] = json.loads(r_dict["metadata"])
                runs.append(r_dict)
            return runs

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM runs WHERE id = ?", (run_id,))
            run_row = cursor.fetchone()
            if not run_row:
                return None

            run_dict = dict(run_row)
            if isinstance(run_dict.get("metadata"), str):
                run_dict["metadata"] = json.loads(run_dict["metadata"])

            cursor.execute("SELECT * FROM evaluation_results WHERE run_id = ?", (run_id,))
            results = []
            for res_row in cursor.fetchall():
                res_dict = dict(res_row)
                res_dict["passed"] = bool(res_dict["passed"])
                if isinstance(res_dict.get("metadata"), str):
                    res_dict["metadata"] = json.loads(res_dict["metadata"])
                
                # Fetch metrics
                cursor.execute("SELECT * FROM metric_scores WHERE evaluation_result_id = ?", (res_dict["id"],))
                metrics = []
                for m in cursor.fetchall():
                    m_dict = dict(m)
                    m_dict["passed"] = bool(m_dict["passed"])
                    if isinstance(m_dict.get("metadata"), str):
                        m_dict["metadata"] = json.loads(m_dict["metadata"])
                    metrics.append(m_dict)
                res_dict["metrics"] = metrics
                
                # Fetch trajectory if exists
                if res_dict["trajectory_id"]:
                    cursor.execute("SELECT * FROM trajectories WHERE id = ?", (res_dict["trajectory_id"],))
                    traj_row = cursor.fetchone()
                    if traj_row:
                        traj_dict = dict(traj_row)
                        traj_dict["steps"] = json.loads(traj_dict["steps_json"])
                        if isinstance(traj_dict.get("metadata"), str):
                            traj_dict["metadata"] = json.loads(traj_dict["metadata"])
                        res_dict["trajectory"] = traj_dict
                
                results.append(res_dict)

            run_dict["results"] = results
            return run_dict

    def delete_run(self, run_id: str):
        with self._connection() as conn:
            with conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM metric_scores WHERE evaluation_result_id IN (SELECT id FROM evaluation_results WHERE run_id = ?)", (run_id,))
                cursor.execute("DELETE FROM evaluation_results WHERE run_id = ?", (run_id,))
                cursor.execute("DELETE FROM runs WHERE id = ?", (run_id,))


class PostgresStorage:
    """Postgres storage engine for OpenHarness evaluation traces and metrics."""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self._init_db()

    def _get_connection(self):
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "PostgreSQL driver 'psycopg2' not found. "
                "Please install psycopg2 or psycopg2-binary to use Postgres storage."
            )
        conn = psycopg2.connect(self.db_url)
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS runs (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        timestamp DOUBLE PRECISION NOT NULL,
                        passed_count INTEGER DEFAULT 0,
                        failed_count INTEGER DEFAULT 0,
                        total_count INTEGER DEFAULT 0,
                        duration_ms DOUBLE PRECISION DEFAULT 0.0,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS evaluation_results (
                        id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        test_case_name TEXT NOT NULL,
                        passed INTEGER NOT NULL,
                        total_score DOUBLE PRECISION NOT NULL,
                        duration_ms DOUBLE PRECISION NOT NULL,
                        timestamp DOUBLE PRECISION NOT NULL,
                        trajectory_id TEXT,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS trajectories (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        input_prompt TEXT,
                        final_output TEXT,
                        total_duration_ms DOUBLE PRECISION,
                        total_prompt_tokens INTEGER,
                        total_completion_tokens INTEGER,
                        steps_json TEXT,
                        metadata TEXT
                    )
                """)
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS metric_scores (
                        id SERIAL PRIMARY KEY,
                        evaluation_result_id TEXT NOT NULL,
                        name TEXT NOT NULL,
                        score DOUBLE PRECISION NOT NULL,
                        passed INTEGER NOT NULL,
                        reason TEXT,
                        category TEXT,
                        metadata TEXT
                    )
                """)
            conn.commit()

    def save_run(self, run_id: str, name: str, results: List[EvaluationResult], metadata: Optional[Dict[str, Any]] = None):
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        total_duration = sum(r.duration_ms for r in results)
        
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO runs (id, name, timestamp, passed_count, failed_count, total_count, duration_ms, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        name = EXCLUDED.name,
                        timestamp = EXCLUDED.timestamp,
                        passed_count = EXCLUDED.passed_count,
                        failed_count = EXCLUDED.failed_count,
                        total_count = EXCLUDED.total_count,
                        duration_ms = EXCLUDED.duration_ms,
                        metadata = EXCLUDED.metadata
                """, (
                    run_id,
                    name,
                    time.time(),
                    passed_count,
                    failed_count,
                    len(results),
                    total_duration,
                    json.dumps(metadata or {})
                ))

                for result in results:
                    traj_id = None
                    if result.trajectory:
                        traj_id = result.trajectory.id
                        cursor.execute("""
                            INSERT INTO trajectories 
                            (id, name, input_prompt, final_output, total_duration_ms, total_prompt_tokens, total_completion_tokens, steps_json, metadata)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (id) DO UPDATE SET
                                name = EXCLUDED.name,
                                input_prompt = EXCLUDED.input_prompt,
                                final_output = EXCLUDED.final_output,
                                total_duration_ms = EXCLUDED.total_duration_ms,
                                total_prompt_tokens = EXCLUDED.total_prompt_tokens,
                                total_completion_tokens = EXCLUDED.total_completion_tokens,
                                steps_json = EXCLUDED.steps_json,
                                metadata = EXCLUDED.metadata
                        """, (
                            result.trajectory.id,
                            result.trajectory.name,
                            result.trajectory.input_prompt,
                            result.trajectory.final_output,
                            result.trajectory.total_duration_ms,
                            result.trajectory.total_prompt_tokens,
                            result.trajectory.total_completion_tokens,
                            json.dumps([s.model_dump() for s in result.trajectory.steps]),
                            json.dumps(result.trajectory.metadata)
                        ))

                    cursor.execute("""
                        INSERT INTO evaluation_results
                        (id, run_id, test_case_name, passed, total_score, duration_ms, timestamp, trajectory_id, metadata)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            run_id = EXCLUDED.run_id,
                            test_case_name = EXCLUDED.test_case_name,
                            passed = EXCLUDED.passed,
                            total_score = EXCLUDED.total_score,
                            duration_ms = EXCLUDED.duration_ms,
                            timestamp = EXCLUDED.timestamp,
                            trajectory_id = EXCLUDED.trajectory_id,
                            metadata = EXCLUDED.metadata
                    """, (
                        result.id,
                        run_id,
                        result.test_case_name,
                        1 if result.passed else 0,
                        result.total_score,
                        result.duration_ms,
                        result.timestamp,
                        traj_id,
                        json.dumps(result.metadata)
                    ))

                    for m in result.metrics:
                        cursor.execute("""
                            INSERT INTO metric_scores (evaluation_result_id, name, score, passed, reason, category, metadata)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                        """, (
                            result.id,
                            m.name,
                            m.score,
                            1 if m.passed else 0,
                            m.reason,
                            m.category,
                            json.dumps(m.metadata)
                        ))
            conn.commit()

    def get_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM runs ORDER BY timestamp DESC LIMIT %s", (limit,))
                rows = cursor.fetchall()
                runs = []
                for r in rows:
                    r_dict = dict(r)
                    if isinstance(r_dict.get("metadata"), str):
                        r_dict["metadata"] = json.loads(r_dict["metadata"])
                    runs.append(r_dict)
                return runs

    def get_run_details(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            from psycopg2.extras import RealDictCursor
            with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute("SELECT * FROM runs WHERE id = %s", (run_id,))
                run_row = cursor.fetchone()
                if not run_row:
                    return None

                run_dict = dict(run_row)
                if isinstance(run_dict.get("metadata"), str):
                    run_dict["metadata"] = json.loads(run_dict["metadata"])

                cursor.execute("SELECT * FROM evaluation_results WHERE run_id = %s", (run_id,))
                results = []
                for res_row in cursor.fetchall():
                    res_dict = dict(res_row)
                    res_dict["passed"] = bool(res_dict["passed"])
                    if isinstance(res_dict.get("metadata"), str):
                        res_dict["metadata"] = json.loads(res_dict["metadata"])
                    
                    # Fetch metrics
                    cursor.execute("SELECT * FROM metric_scores WHERE evaluation_result_id = %s", (res_dict["id"],))
                    metrics = []
                    for m in cursor.fetchall():
                        m_dict = dict(m)
                        m_dict["passed"] = bool(m_dict["passed"])
                        if isinstance(m_dict.get("metadata"), str):
                            m_dict["metadata"] = json.loads(m_dict["metadata"])
                        metrics.append(m_dict)
                    res_dict["metrics"] = metrics
                    
                    # Fetch trajectory if exists
                    if res_dict["trajectory_id"]:
                        cursor.execute("SELECT * FROM trajectories WHERE id = %s", (res_dict["trajectory_id"],))
                        traj_row = cursor.fetchone()
                        if traj_row:
                            traj_dict = dict(traj_row)
                            traj_dict["steps"] = json.loads(traj_dict["steps_json"])
                            if isinstance(traj_dict.get("metadata"), str):
                                traj_dict["metadata"] = json.loads(traj_dict["metadata"])
                            res_dict["trajectory"] = traj_dict
                    
                    results.append(res_dict)

                run_dict["results"] = results
                return run_dict

    def delete_run(self, run_id: str):
        with self._get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM metric_scores WHERE evaluation_result_id IN (SELECT id FROM evaluation_results WHERE run_id = %s)", (run_id,))
                cursor.execute("DELETE FROM evaluation_results WHERE run_id = %s", (run_id,))
                cursor.execute("DELETE FROM runs WHERE id = %s", (run_id,))
            conn.commit()


StorageEngine.register(SQLiteStorage)
StorageEngine.register(PostgresStorage)
