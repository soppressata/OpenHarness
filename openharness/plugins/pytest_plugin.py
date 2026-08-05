import pytest
import time
from openharness.core.storage import StorageEngine
from openharness.core.types import EvaluationResult, MetricScore


def pytest_addoption(parser):
    group = parser.getgroup("openharness", "OpenHarness Evaluation Harness")
    group.addoption(
        "--openharness",
        action="store_true",
        default=False,
        help="Enable OpenHarness evaluation tracking and local storage."
    )
    group.addoption(
        "--openharness-db",
        action="store",
        default=".openharness/evals.db",
        help="Database path for storing evaluation results."
    )


class PytestHarnessPlugin:
    def __init__(self, db_path: str):
        self.storage = StorageEngine(db_path=db_path)
        self.run_id = f"pytest_{int(time.time())}"
        self.results = []

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()

        if report.when == "call":
            passed = report.passed
            duration_ms = report.duration * 1000.0
            test_name = item.name

            # Check if custom metrics were attached to item by test
            metrics = getattr(item, "_openharness_metrics", [])
            if not metrics:
                metrics.append(MetricScore(
                    name="pytest_status",
                    score=1.0 if passed else 0.0,
                    passed=passed,
                    reason=f"Pytest assertion result: {report.outcome}",
                    category="assertion"
                ))

            res = EvaluationResult(
                run_id=self.run_id,
                test_case_name=test_name,
                metrics=metrics,
                passed=passed,
                total_score=1.0 if passed else 0.0,
                duration_ms=duration_ms
            )
            self.results.append(res)

    def pytest_sessionfinish(self, session, exitstatus):
        if self.results:
            self.storage.save_run(
                run_id=self.run_id,
                name=f"Pytest Session {session.config.rootpath.name}",
                results=self.results,
                metadata={"exitstatus": exitstatus}
            )


def pytest_configure(config):
    if config.getoption("--openharness"):
        db_path = config.getoption("--openharness-db")
        config._openharness = PytestHarnessPlugin(db_path=db_path)
        config.pluginmanager.register(config._openharness)
