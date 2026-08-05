import pytest
from openharness.core.storage import StorageEngine
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
