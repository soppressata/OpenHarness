import pytest
import asyncio
from openharness import Harness, MetricScore


def test_async_run_case(tmp_path):
    async def _async_test():
        db_file = str(tmp_path / "async.db")
        h = Harness(name="Async Suite", db_path=db_file)

        async def async_agent(prompt: str):
            await asyncio.sleep(0.001)
            return f"Echo: {prompt}"

        async def async_evaluator(target):
            await asyncio.sleep(0.001)
            return MetricScore(
                name="async_check",
                score=1.0,
                passed=True,
                reason="Async evaluation passed",
                category="assertion"
            )

        res = await h.async_run_case(
            test_case_name="Async Test Case",
            agent_fn=async_agent,
            input_data="Hello Async",
            evaluators=[async_evaluator]
        )

        assert res.passed is True
        assert res.total_score == 1.0

    asyncio.run(_async_test())
