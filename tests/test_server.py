import pytest
from fastapi.testclient import TestClient
from openharness.server.app import create_app
from openharness.core.storage import StorageEngine
from openharness.core.types import EvaluationResult, MetricScore, Trajectory, Step


def test_server_endpoints(tmp_path):
    db_file = str(tmp_path / "server_test.db")
    storage = StorageEngine(db_path=db_file)

    res = EvaluationResult(
        run_id="run_srv_1",
        test_case_name="Server Case",
        trajectory=Trajectory(input_prompt="Hi", steps=[Step(step_index=1, content="Hello")], final_output="Hello"),
        metrics=[MetricScore(name="m", score=1.0, passed=True, reason="OK")],
        passed=True,
        total_score=1.0,
        duration_ms=10.0
    )
    storage.save_run(run_id="run_srv_1", name="Server Suite", results=[res])

    app = create_app(db_path=db_file)
    client = TestClient(app)

    # List runs
    resp = client.get("/api/runs")
    assert resp.status_code == 200
    runs = resp.json()
    assert len(runs) == 1
    assert runs[0]["id"] == "run_srv_1"

    # Get run details
    resp_details = client.get("/api/runs/run_srv_1")
    assert resp_details.status_code == 200
    assert resp_details.json()["name"] == "Server Suite"

    # Export run JSON
    resp_export = client.get("/api/runs/run_srv_1/export?format=json")
    assert resp_export.status_code == 200

    # Analytics
    resp_analytics = client.get("/api/runs/run_srv_1/analytics")
    assert resp_analytics.status_code == 200

    # Delete run
    resp_del = client.delete("/api/runs/run_srv_1")
    assert resp_del.status_code == 200

    # Verify deleted
    assert client.get("/api/runs/run_srv_1").status_code == 404
