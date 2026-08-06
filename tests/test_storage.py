import pytest
import os
import sys
import time
import concurrent.futures
from unittest.mock import MagicMock
from openharness.core.storage import StorageEngine, SQLiteStorage, PostgresStorage
from openharness.core.types import EvaluationResult, MetricScore, Trajectory, Step, ToolCall


def test_storage_engine(tmp_path):
    db_file = str(tmp_path / "test.db")
    storage = StorageEngine(db_path=db_file)

    traj = Trajectory(
        input_prompt="Translate hello to spanish",
        steps=[Step(step_index=1, step_type="agent_response", content="Hola")],
        final_output="Hola"
    )

    res = EvaluationResult(
        run_id="run_100",
        test_case_name="Translate Test",
        trajectory=traj,
        metrics=[MetricScore(name="exact", score=1.0, passed=True, reason="Matched")],
        passed=True,
        total_score=1.0,
        duration_ms=12.5
    )

    storage.save_run(run_id="run_100", name="Translation Suite", results=[res])

    runs = storage.get_runs()
    assert len(runs) == 1
    assert runs[0]["id"] == "run_100"
    assert runs[0]["passed_count"] == 1

    details = storage.get_run_details("run_100")
    assert details is not None
    assert len(details["results"]) == 1
    assert details["results"][0]["test_case_name"] == "Translate Test"


def thread_write_worker(db_file, worker_id):
    storage = StorageEngine(db_path=db_file)
    for i in range(10):
        res = EvaluationResult(
            run_id=f"run_thread_w{worker_id}_{i}",
            test_case_name=f"Thread Case {i}",
            trajectory=None,
            metrics=[],
            passed=True,
            total_score=1.0,
            duration_ms=1.5
        )
        storage.save_run(
            run_id=f"run_thread_w{worker_id}_{i}",
            name=f"Thread Worker {worker_id} Run {i}",
            results=[res]
        )


def test_storage_concurrency_threads(tmp_path):
    db_file = str(tmp_path / "concurrent_thread.db")
    # Initialize DB schema
    StorageEngine(db_path=db_file)

    # Use ThreadPoolExecutor to run 10 threads concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(thread_write_worker, db_file, i) for i in range(10)]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    storage = StorageEngine(db_path=db_file)
    runs = storage.get_runs(limit=200)
    assert len(runs) == 100


def process_write_worker(db_file, worker_id):
    storage = StorageEngine(db_path=db_file)
    for i in range(10):
        res = EvaluationResult(
            run_id=f"run_proc_w{worker_id}_{i}",
            test_case_name=f"Proc Case {i}",
            trajectory=None,
            metrics=[],
            passed=True,
            total_score=1.0,
            duration_ms=1.5
        )
        storage.save_run(
            run_id=f"run_proc_w{worker_id}_{i}",
            name=f"Proc Worker {worker_id} Run {i}",
            results=[res]
        )


def test_storage_concurrency_processes(tmp_path):
    db_file = str(tmp_path / "concurrent_proc.db")
    # Initialize DB schema
    StorageEngine(db_path=db_file)

    # Use ProcessPoolExecutor to run 5 processes concurrently
    with concurrent.futures.ProcessPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(process_write_worker, db_file, i) for i in range(5)]
        for future in concurrent.futures.as_completed(futures):
            future.result()

    storage = StorageEngine(db_path=db_file)
    runs = storage.get_runs(limit=100)
    assert len(runs) == 50


def test_storage_factory_postgres(monkeypatch):
    mock_psycopg2 = MagicMock()
    mock_conn = MagicMock()
    mock_psycopg2.connect.return_value = mock_conn
    
    monkeypatch.setitem(sys.modules, "psycopg2", mock_psycopg2)
    monkeypatch.setenv("OPENHARNESS_DB_URL", "postgresql://user:pass@host/db")
    
    storage = StorageEngine()
    assert isinstance(storage, PostgresStorage)
    assert storage.db_url == "postgresql://user:pass@host/db"
    assert mock_psycopg2.connect.called


@pytest.mark.skipif(not os.environ.get("OPENHARNESS_DB_URL"), reason="OPENHARNESS_DB_URL not set")
def test_postgres_storage_integration():
    db_url = os.environ["OPENHARNESS_DB_URL"]
    storage = StorageEngine()
    assert isinstance(storage, PostgresStorage)

    # Test basic writes and reads
    res = EvaluationResult(
        run_id="run_pg_1",
        test_case_name="Postgres Test",
        trajectory=Trajectory(
            input_prompt="PG Test",
            steps=[Step(step_index=1, step_type="agent_response", content="OK")],
            final_output="OK"
        ),
        metrics=[MetricScore(name="exact", score=1.0, passed=True, reason="Matched")],
        passed=True,
        total_score=1.0,
        duration_ms=5.0
    )
    storage.save_run(run_id="run_pg_1", name="PG Run Suite", results=[res])

    runs = storage.get_runs()
    assert len(runs) >= 1
    assert any(r["id"] == "run_pg_1" for r in runs)

    details = storage.get_run_details("run_pg_1")
    assert details is not None
    assert details["name"] == "PG Run Suite"
    assert len(details["results"]) == 1
    assert details["results"][0]["test_case_name"] == "Postgres Test"
    assert details["results"][0]["metrics"][0]["name"] == "exact"
    assert details["results"][0]["trajectory"]["final_output"] == "OK"

    storage.delete_run("run_pg_1")
    assert storage.get_run_details("run_pg_1") is None
