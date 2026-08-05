import json
import re
from typing import Callable, Union, Optional, Dict
from openharness.core.types import MetricScore, Trajectory
from openharness.providers import get_provider
from openharness.providers.base import BaseProvider


def llm_judge(
    rubric: str,
    model: Union[str, BaseProvider] = "ollama/llama3.1",
    score_threshold: float = 0.7,
    use_cache: bool = True,
    effort: str = "low"
) -> Callable[[Union[str, Trajectory]], MetricScore]:
    """
    Evaluator: LLM-as-a-Judge evaluator using local or cloud LLMs with context caching & low effort budgeting.
    """
    provider = get_provider(model)

    def evaluator(target: Union[str, Trajectory]) -> MetricScore:
        actual = target.final_output if isinstance(target, Trajectory) else str(target)
        prompt = f"""You are an AI Judge. Evaluate output against rubric.

[RUBRIC]
{rubric}

[OUTPUT]
{actual}

Return JSON: {{"score": float 0-1, "reason": "summary", "passed": bool}}"""

        try:
            res = provider.generate(
                prompt=prompt,
                system_prompt="AI Judge. Output valid JSON only.",
                temperature=0.0,
                use_cache=use_cache,
                effort=effort
            )
            raw = res.content.strip()
            
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                raw = match.group(0)

            data = json.loads(raw)
            score = float(data.get("score", 0.0))
            passed = bool(data.get("passed", score >= score_threshold))
            reason = data.get("reason", "LLM Judge evaluation completed.")

            return MetricScore(
                name=f"llm_judge:{rubric[:20].strip()}",
                score=score,
                passed=passed,
                reason=reason,
                category="llm_judge",
                metadata={
                    "model": getattr(provider, "model", str(model)),
                    "tokens": res.prompt_tokens + res.completion_tokens,
                    "cached_tokens": res.cached_tokens,
                    "effort": effort
                }
            )
        except Exception as e:
            return MetricScore(
                name="llm_judge",
                score=0.0,
                passed=False,
                reason=f"LLM Judge execution failed: {str(e)}",
                category="llm_judge"
            )

    return evaluator


def pairwise_arena_judge(
    rubric: str,
    output_a: str,
    output_b: str,
    model: Union[str, BaseProvider] = "ollama/llama3.1",
    use_cache: bool = True,
    effort: str = "low"
) -> MetricScore:
    """Head-to-head pairwise arena judging between two agent outputs with context caching."""
    provider = get_provider(model)
    prompt = f"""Compare A vs B under rubric.

[RUBRIC]
{rubric}

[A]
{output_a}

[B]
{output_b}

Return JSON: {{"winner": "A"|"B"|"TIE", "reason": "brief summary"}}"""

    try:
        res = provider.generate(prompt=prompt, temperature=0.0, use_cache=use_cache, effort=effort)
        raw = res.content.strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            raw = match.group(0)
        data = json.loads(raw)
        return MetricScore(
            name="pairwise_arena",
            score=1.0 if data.get("winner") == "A" else 0.5,
            passed=data.get("winner") != "B",
            reason=f"Winner: {data.get('winner')}. Reason: {data.get('reason')}",
            category="llm_judge",
            metadata={"cached_tokens": res.cached_tokens, "effort": effort}
        )
    except Exception as e:
        return MetricScore(
            name="pairwise_arena",
            score=0.0,
            passed=False,
            reason=f"Pairwise arena judging failed: {str(e)}",
            category="llm_judge"
        )
