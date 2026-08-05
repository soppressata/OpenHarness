import json
import pytest
from openharness import Dataset, eval_dataset, assert_exact_match


def test_dataset_creation_and_jsonl(tmp_path):
    ds = Dataset(name="TestDS")
    ds.add_case("case1", "input1", "expected1")
    ds.add_case("case2", "input2", "expected2")
    assert len(ds.cases) == 2

    jsonl_file = str(tmp_path / "data.jsonl")
    ds.to_jsonl(jsonl_file)

    loaded_ds = Dataset.from_jsonl(jsonl_file)
    assert len(loaded_ds.cases) == 2
    assert loaded_ds.cases[0].name == "case1"


def test_dataset_from_json(tmp_path):
    json_file = str(tmp_path / "data.json")
    data = [
        {"name": "c1", "input": "in1", "expected_output": "out1"},
        {"name": "c2", "input": "in2", "expected_output": "out2"}
    ]
    with open(json_file, "w") as f:
        json.dump(data, f)

    ds = Dataset.from_json(json_file)
    assert len(ds.cases) == 2
    assert ds.cases[1].name == "c2"


def test_eval_dataset(tmp_path):
    db_file = str(tmp_path / "ds_evals.db")
    ds = Dataset(name="BatchDS")
    ds.add_case("Echo 1", "hello", "hello")
    ds.add_case("Echo 2", "world", "world")

    results = eval_dataset(
        dataset=ds,
        agent_fn=lambda x: str(x),
        evaluators=[assert_exact_match("hello")],
        db_path=db_file
    )

    assert len(results) == 2
    assert results[0].passed is True
    assert results[1].passed is False
