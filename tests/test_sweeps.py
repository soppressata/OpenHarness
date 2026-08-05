import pytest
from openharness import run_determinism_sweep, assert_exact_match


def test_determinism_sweep(tmp_path):
    db_file = str(tmp_path / "sweep.db")
    counter = 0

    def flaky_agent(input_data):
        nonlocal counter
        counter += 1
        return "Pass" if counter % 2 == 1 else "Fail"

    sweep = run_determinism_sweep(
        test_case_name="Flaky Test",
        agent_fn=flaky_agent,
        input_data="query",
        evaluators=[assert_exact_match("Pass")],
        n_runs=4,
        db_path=db_file
    )

    assert sweep.n_runs == 4
    assert sweep.passed_runs == 2
    assert sweep.failed_runs == 2
    assert sweep.pass_rate == 0.5
    assert sweep.flakiness_score == 1.0  # Max flakiness
