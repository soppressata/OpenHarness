import json
import re
from typing import Callable, Union, Optional
from openharness.core.types import MetricScore, Trajectory
from openharness.providers import get_provider, BaseProvider


DEFAULT_JUDGE_PROMPT = """
You are an expert AI Evaluator judging an AI Agent's performance.

[USER INPUT / CONTEXT]:
{input_prompt}

[AGENT TRAJECTORY / OUTPUT]:
{agent_output}

[RUBRIC]:
{rubric}

Carefully analyze the output against the rubric. Output your evaluation in JSON format with two keys:
- "score": A floating point number between 0.0 (fail/terrible) and 1.0 (perfect/complete pass).
- "passed": A boolean (true if score >= 0.7, false otherwise).
- "reason": A short explanation justifying your score.

JSON output:
"""


def llm_judge(
    rubric: str,
    model: str = "ollama/llama3.1",
    provider: Optional[BaseProvider] = None,
    name: str = "llm_judge"
) -> Callable[[Union[str, Trajectory]], MetricScore]:
    """LLM-as-a-Judge evaluator using local LLMs (Ollama/vLLM) or Cloud APIs."""

    llm_provider = provider or get_provider(model)

    def evaluator(target: Union[str, Trajectory]) -> MetricScore:
        if isinstance(target, Trajectory):
            input_prompt = target.input_prompt
            agent_output = target.final_output or str(target.steps)
        else:
            input_prompt = "N/A"
            agent_output = str(target)

        prompt = DEFAULT_JUDGE_PROMPT.format(
            input_prompt=input_prompt,
            agent_output=agent_output,
            rubric=rubric
        )

        try:
            response = llm_provider.generate(
                prompt=prompt,
                system_prompt="You are a strict, objective AI evaluation judge.",
                temperature=0.0
            )

            content = response.content.strip()
            
            # Extract JSON block
            json_match = re.search(r"\{.*\}", content, re.DOTALL)
            if json_match:
                content = json_match.group(0)

            parsed = json.loads(content)
            score = float(parsed.get("score", 0.0))
            score = max(0.0, min(1.0, score))
            passed = bool(parsed.get("passed", score >= 0.7))
            reason = str(parsed.get("reason", "No reason provided by LLM judge."))

            return MetricScore(
                name=name,
                score=score,
                passed=passed,
                reason=f"[Judge Model: {response.model}] {reason}",
                category="llm_judge"
            )
        except Exception as e:
            # Fallback for judge parsing errors or local model absence
            return MetricScore(
                name=name,
                score=0.0,
                passed=False,
                reason=f"LLM Judge evaluation failed: {str(e)}",
                category="llm_judge"
            )

    return evaluator


def pairwise_arena_judge(
    rubric: str,
    model: str = "ollama/llama3.1",
    provider: Optional[BaseProvider] = None
) -> Callable[[Trajectory, Trajectory], MetricScore]:
    """Pairwise Arena Judge: Compare Trajectory A vs Trajectory B to determine winner."""
    
    llm_provider = provider or get_provider(model)

    def evaluator(traj_a: Trajectory, traj_b: Trajectory) -> MetricScore:
        prompt = f"""
Compare the two AI Agent outputs for the user prompt:
USER PROMPT: {traj_a.input_prompt}

AGENT A OUTPUT:
{traj_a.final_output}

AGENT B OUTPUT:
{traj_b.final_output}

RUBRIC:
{rubric}

Respond in JSON with:
- "winner": "A", "B", or "TIE"
- "reason": Explanation of why one agent outperformed the other.
"""
        try:
            response = llm_provider.generate(prompt=prompt, temperature=0.0)
            json_match = re.search(r"\{.*\}", response.content, re.DOTALL)
            content = json_match.group(0) if json_match else response.content
            parsed = json.loads(content)

            winner = parsed.get("winner", "TIE")
            reason = parsed.get("reason", "")

            return MetricScore(
                name="pairwise_arena",
                score=1.0 if winner == "A" else (0.5 if winner == "TIE" else 0.0),
                passed=winner != "B",
                reason=f"Winner: {winner}. {reason}",
                category="llm_judge"
            )
        except Exception as e:
            return MetricScore(
                name="pairwise_arena",
                score=0.5,
                passed=True,
                reason=f"Pairwise judging failed: {str(e)}",
                category="llm_judge"
            )

    return evaluator
