import pytest
from openharness import Dataset, run_ab_experiment, assert_exact_match


def test_ab_experiment(tmp_path):
    db_file = str(tmp_path / "exp.db")

    ds = Dataset(name="ExpDS")
    ds.add_case("C1", "hello", "hello")
    ds.add_case("C2", "world", "world")

    agent_a = lambda x: "hello" if x == "hello" else "wrong"
    agent_b = lambda x: str(x)  # Perfect echo

    exp = run_ab_experiment(
        experiment_name="Prompt V1 vs V2",
        variant_a_name="Prompt V1",
        agent_a_fn=agent_a,
        variant_b_name="Prompt V2",
        agent_b_fn=agent_b,
        dataset=ds,
        evaluators=[assert_exact_match(expected="hello")], # Evaluates against hello
        db_path=db_file
    )

    assert exp.experiment_name == "Prompt V1 vs V2"
    assert exp.total_cases == 2
    assert len(exp.diff_details) == 2
