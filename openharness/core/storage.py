import json
import os
import sqlite3
import time
from typing import Any, Dict, List, Optional
from openharness.core.types import EvaluationResult, MetricScore, Trajectory, Step, ToolCall


class StorageEngine:
    """Embedded SQLite storage engine for OpenHarness evaluation traces and metrics."""

    def __init__(self, db_path: str = ".openharness/evals.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
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
            conn.commit()

    def save_run(self, run_id: str, name: str, results: List[EvaluationResult], metadata: Optional[Dict[str, Any]] = None):
        passed_count = sum(1 for r in results if r.passed)
        failed_count = len(results) - passed_count
        total_duration = sum(r.duration_ms for r in results)
        
        with self._get_connection() as conn:
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

            conn.commit()

    def get_runs(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
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
        with self._get_connection() as conn:
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
