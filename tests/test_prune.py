import sqlite3
import time

from click.testing import CliRunner

from openharness.cli.main import cli
from openharness.core.storage import StorageEngine
from openharness.core.types import EvaluationResult, MetricScore, Step, Trajectory


def _make_result(run_id: str, with_trajectory: bool = True) -> EvaluationResult:
    trajectory = None
    if with_trajectory:
        trajectory = Trajectory(
            input_prompt="prompt",
            steps=[Step(step_index=1, step_type="agent_response", content="ok")],
            final_output="ok",
        )
    return EvaluationResult(
        run_id=run_id,
        test_case_name="Case",
        trajectory=trajectory,
        metrics=[MetricScore(name="exact", score=1.0, passed=True, reason="matched")],
        passed=True,
        total_score=1.0,
        duration_ms=1.0,
    )


def _seed_run(storage, run_id: str, age_days: float) -> None:
    """Persist a run and backdate its timestamp so it is ``age_days`` old."""
    storage.save_run(run_id=run_id, name=f"Suite {run_id}", results=[_make_result(run_id)])
    conn = storage._get_connection()
    conn.execute("UPDATE runs SET timestamp = ? WHERE id = ?", (time.time() - age_days * 86400.0, run_id))
    conn.commit()
    conn.close()


def _build_db(path: str, ages: dict) -> StorageEngine:
    storage = StorageEngine(db_path=path)
    for run_id, age in ages.items():
        _seed_run(storage, run_id, age)
    return storage


def _sql_counts(db_path: str):
    conn = sqlite3.connect(db_path)
    counts = {
        "runs": conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
        "evaluation_results": conn.execute("SELECT COUNT(*) FROM evaluation_results").fetchone()[0],
        "trajectories": conn.execute("SELECT COUNT(*) FROM trajectories").fetchone()[0],
        "metric_scores": conn.execute("SELECT COUNT(*) FROM metric_scores").fetchone()[0],
    }
    conn.close()
    return counts


def test_delete_runs_before_only_older(tmp_path):
    storage = StorageEngine(db_path=str(tmp_path / "prune.db"))
    _seed_run(storage, "old_run", age_days=100)
    _seed_run(storage, "recent_run", age_days=2)
    _seed_run(storage, "now_run", age_days=0)

    deleted = storage.delete_runs_before(time.time() - 30 * 86400.0)

    assert deleted == 1
    remaining = [r["id"] for r in storage.get_runs(limit=100)]
    assert remaining == ["now_run", "recent_run"]


def test_delete_runs_before_strictly_older(tmp_path):
    storage = StorageEngine(db_path=str(tmp_path / "strict.db"))
    _seed_run(storage, "run_a", age_days=0)
    _seed_run(storage, "run_b", age_days=0)
    threshold = time.time()
    conn = storage._get_connection()
    conn.execute("UPDATE runs SET timestamp = ? WHERE id = 'run_a'", (threshold,))
    conn.execute("UPDATE runs SET timestamp = ? WHERE id = 'run_b'", (threshold - 1.0,))
    conn.commit()
    conn.close()

    deleted = storage.delete_runs_before(threshold)

    assert deleted == 1
    remaining = [r["id"] for r in storage.get_runs(limit=100)]
    assert "run_a" in remaining
    assert "run_b" not in remaining


def test_delete_run_cascades_to_trajectories(tmp_path):
    db_file = str(tmp_path / "cascade.db")
    storage = StorageEngine(db_path=db_file)
    _seed_run(storage, "run_traj", age_days=0)
    _seed_run(storage, "other", age_days=0)

    storage.delete_run("run_traj")

    conn = sqlite3.connect(db_file)
    orphan_trajs = conn.execute(
        "SELECT COUNT(*) FROM trajectories t "
        "WHERE NOT EXISTS (SELECT 1 FROM evaluation_results e WHERE e.trajectory_id = t.id)"
    ).fetchone()[0]
    orphan_metrics = conn.execute(
        "SELECT COUNT(*) FROM metric_scores ms "
        "WHERE NOT EXISTS (SELECT 1 FROM evaluation_results e WHERE e.id = ms.evaluation_result_id)"
    ).fetchone()[0]
    conn.close()

    assert storage.get_run_details("run_traj") is None
    assert storage.get_run_details("other") is not None
    assert orphan_trajs == 0
    assert orphan_metrics == 0


def test_delete_runs_before_no_orphaned_rows(tmp_path):
    db_file = str(tmp_path / "cascade2.db")
    storage = StorageEngine(db_path=db_file)
    _seed_run(storage, "old_a", age_days=100)
    _seed_run(storage, "old_b", age_days=90)
    _seed_run(storage, "fresh", age_days=1)

    deleted = storage.delete_runs_before(time.time() - 30 * 86400.0)

    assert deleted == 2
    conn = sqlite3.connect(db_file)
    orphan_trajs = conn.execute(
        "SELECT COUNT(*) FROM trajectories t "
        "WHERE NOT EXISTS (SELECT 1 FROM evaluation_results e WHERE e.trajectory_id = t.id)"
    ).fetchone()[0]
    orphan_results = conn.execute(
        "SELECT COUNT(*) FROM evaluation_results e "
        "WHERE NOT EXISTS (SELECT 1 FROM runs r WHERE r.id = e.run_id)"
    ).fetchone()[0]
    orphan_metrics = conn.execute(
        "SELECT COUNT(*) FROM metric_scores ms "
        "WHERE NOT EXISTS (SELECT 1 FROM evaluation_results e WHERE e.id = ms.evaluation_result_id)"
    ).fetchone()[0]
    conn.close()
    assert orphan_trajs == 0
    assert orphan_results == 0
    assert orphan_metrics == 0


def test_cli_prune_help_documents_options():
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--help"])
    assert result.exit_code == 0
    assert "--older-than" in result.output
    assert "--run-id" in result.output
    assert "--dry-run" in result.output
    assert "--db" in result.output


def test_cli_prune_empty_db(tmp_path):
    db_file = str(tmp_path / "empty.db")
    StorageEngine(db_path=db_file)
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--older-than", "30", "--db", db_file])
    assert result.exit_code == 0
    assert "Nothing to prune" in result.output


def test_cli_prune_dry_run_noop(tmp_path):
    db_file = str(tmp_path / "dry.db")
    _build_db(db_file, {"old_a": 100, "new_a": 2})
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--older-than", "30", "--dry-run", "--db", db_file])
    assert result.exit_code == 0
    assert "old_a" in result.output
    assert "Dry run: no changes made." in result.output
    assert _sql_counts(db_file)["runs"] == 2


def test_cli_prune_older_than(tmp_path):
    db_file = str(tmp_path / "older.db")
    _build_db(db_file, {"old_a": 100, "old_b": 90, "new_a": 2})
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--older-than", "30", "--db", db_file])
    assert result.exit_code == 0
    assert "Pruned 2 run(s)" in result.output

    remaining = [r["id"] for r in StorageEngine(db_path=db_file).get_runs(limit=100)]
    assert remaining == ["new_a"]


def test_cli_prune_run_id(tmp_path):
    db_file = str(tmp_path / "runid.db")
    _build_db(db_file, {"keep": 100, "remove": 100})
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--run-id", "remove", "--db", db_file])
    assert result.exit_code == 0
    assert "Pruned 1 run(s)" in result.output

    remaining = [r["id"] for r in StorageEngine(db_path=db_file).get_runs(limit=100)]
    assert remaining == ["keep"]


def test_cli_prune_unknown_run_id(tmp_path):
    db_file = str(tmp_path / "unknown.db")
    _build_db(db_file, {"keep": 0})
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--run-id", "missing", "--db", db_file])
    assert result.exit_code == 0
    assert "Nothing to prune" in result.output


def test_cli_prune_requires_filter(tmp_path):
    db_file = str(tmp_path / "req.db")
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--db", db_file])
    assert result.exit_code != 0


def test_cli_prune_cascade(tmp_path):
    db_file = str(tmp_path / "cascade_cli.db")
    _build_db(db_file, {"old_a": 100})
    runner = CliRunner()
    result = runner.invoke(cli, ["prune", "--older-than", "30", "--db", db_file])
    assert result.exit_code == 0
    assert _sql_counts(db_file) == {
        "runs": 0,
        "evaluation_results": 0,
        "trajectories": 0,
        "metric_scores": 0,
    }
