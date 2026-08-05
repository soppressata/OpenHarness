from typing import Dict, Any, Optional
from pydantic import BaseModel
from openharness.core.types import Trajectory

# Pricing per 1M tokens (USD)
MODEL_PRICING: Dict[str, Dict[str, float]] = {
    "gpt-4o": {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
    "claude-3-5-sonnet": {"prompt": 3.00, "completion": 15.00},
    "claude-3-haiku": {"prompt": 0.25, "completion": 1.25},
    "gemini-1.5-pro": {"prompt": 1.25, "completion": 5.00},
    "gemini-1.5-flash": {"prompt": 0.075, "completion": 0.30},
    # Local models are zero cost
    "ollama": {"prompt": 0.0, "completion": 0.0},
    "vllm": {"prompt": 0.0, "completion": 0.0},
    "local": {"prompt": 0.0, "completion": 0.0}
}


class TrajectoryCost(BaseModel):
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_cost_usd: float
    completion_cost_usd: float
    total_cost_usd: float


class LatencyBreakdown(BaseModel):
    total_duration_ms: float
    tool_duration_ms: float
    agent_reasoning_duration_ms: float
    step_durations: Dict[int, float]


def calculate_trajectory_cost(trajectory: Trajectory, default_model: str = "gpt-4o-mini") -> TrajectoryCost:
    """Calculate token usage costs for a given trajectory."""
    prompt_tokens = trajectory.total_prompt_tokens
    completion_tokens = trajectory.total_completion_tokens
    
    # Infer model if available in step metadata
    model_name = default_model
    for step in trajectory.steps:
        if step.model:
            model_name = step.model
            break
        prompt_tokens += step.prompt_tokens
        completion_tokens += step.completion_tokens

    pricing = MODEL_PRICING.get(model_name.lower(), MODEL_PRICING.get("gpt-4o-mini"))
    prompt_cost = (prompt_tokens / 1_000_000) * pricing["prompt"]
    completion_cost = (completion_tokens / 1_000_000) * pricing["completion"]

    return TrajectoryCost(
        model=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
        prompt_cost_usd=round(prompt_cost, 6),
        completion_cost_usd=round(completion_cost, 6),
        total_cost_usd=round(prompt_cost + completion_cost, 6)
    )


def calculate_latency_breakdown(trajectory: Trajectory) -> LatencyBreakdown:
    """Calculate latency waterfall breakdown across agent steps and tool calls."""
    total_ms = trajectory.total_duration_ms or sum(s.duration_ms for s in trajectory.steps)
    tool_ms = 0.0
    step_durations = {}

    for step in trajectory.steps:
        step_durations[step.step_index] = step.duration_ms
        for tc in step.tool_calls:
            tool_ms += tc.duration_ms

    agent_ms = max(0.0, total_ms - tool_ms)

    return LatencyBreakdown(
        total_duration_ms=round(total_ms, 2),
        tool_duration_ms=round(tool_ms, 2),
        agent_reasoning_duration_ms=round(agent_ms, 2),
        step_durations=step_durations
    )
