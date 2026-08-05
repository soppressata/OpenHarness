"""
Dataset module for OpenHarness.
Provides core functionality for the dataset subsystem.
"""
import json
import csv
import os
from typing import Any, Dict, List, Optional, Union
from openharness.core.types import TestCase, EvaluationResult
from openharness.core.harness import Harness, eval_case


class Dataset:
    """Dataset manager for benchmark test cases in OpenHarness."""

    def __init__(self, name: str, cases: Optional[List[TestCase]] = None):
        self.name = name
        self.cases: List[TestCase] = cases or []

    def add_case(self, name: str, input_data: Any, expected_output: Optional[Any] = None, metadata: Optional[Dict[str, Any]] = None):
        self.cases.append(TestCase(
            name=name,
            input=input_data,
            expected_output=expected_output,
            metadata=metadata or {}
        ))

    @classmethod
    def from_jsonl(cls, file_path: str, name: Optional[str] = None) -> "Dataset":
        ds_name = name or os.path.basename(file_path).replace(".jsonl", "")
        cases = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                row = json.loads(line)
                cases.append(TestCase(
                    name=row.get("name", f"case_{len(cases)+1}"),
                    input=row.get("input", row.get("query", "")),
                    expected_output=row.get("expected_output", row.get("target")),
                    metadata=row.get("metadata", {})
                ))
        return cls(name=ds_name, cases=cases)

    @classmethod
    def from_json(cls, file_path: str, name: Optional[str] = None) -> "Dataset":
        ds_name = name or os.path.basename(file_path).replace(".json", "")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        raw_cases = data if isinstance(data, list) else data.get("cases", [])
        cases = [
            TestCase(
                name=c.get("name", f"case_{i+1}"),
                input=c.get("input", ""),
                expected_output=c.get("expected_output"),
                metadata=c.get("metadata", {})
            )
            for i, c in enumerate(raw_cases)
        ]
        return cls(name=ds_name, cases=cases)

    def to_jsonl(self, file_path: str):
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            for case in self.cases:
                f.write(json.dumps(case.model_dump()) + "\n")


def eval_dataset(
    dataset: Dataset,
    agent_fn: Any,
    evaluators: List[Any],
    db_path: str = ".openharness/evals.db"
) -> List[EvaluationResult]:
    """Run batch evaluation over an entire dataset."""
    h = Harness(name=f"Dataset Benchmark: {dataset.name}", db_path=db_path)
    results = []
    for tc in dataset.cases:
        res = h.run_case(
            test_case_name=tc.name,
            agent_fn=agent_fn,
            input_data=tc.input,
            evaluators=evaluators,
            metadata={"expected_output": tc.expected_output, **tc.metadata}
        )
        results.append(res)
    h.save()
    return results
