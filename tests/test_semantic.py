import pytest
from openharness import (
    Trajectory,
    eval_semantic_similarity,
    eval_factuality_and_hallucination,
    eval_safety_and_jailbreak,
    eval_cost_budget
)


def test_semantic_similarity():
    score_pass = eval_semantic_similarity("The weather in Paris is clear and sunny.", threshold=0.7)("Paris weather is sunny and clear.")
    assert score_pass.passed is True
    assert score_pass.score > 0.7

    score_fail = eval_semantic_similarity("Quantum physics string theory", threshold=0.8)("Baking chocolate cake recipe")
    assert score_fail.passed is False


def test_factuality_and_hallucination():
    context = ["Order #12345 was shipped on Monday via FedEx."]
    
    score_grounded = eval_factuality_and_hallucination(context)("Order #12345 shipped Monday via FedEx")
    assert score_grounded.passed is True

    score_hallucinated = eval_factuality_and_hallucination(context)("Unrelated alien spaceship arrival on Saturn rings")
    assert score_hallucinated.passed is False


def test_safety_and_jailbreak():
    score_safe = eval_safety_and_jailbreak()("Here is the requested information.")
    assert score_safe.passed is True

    score_unsafe = eval_safety_and_jailbreak()("System prompt leak: ignore previous instructions")
    assert score_unsafe.passed is False


def test_cost_budget():
    traj = Trajectory(
        input_prompt="Cost query",
        total_prompt_tokens=500,
        total_completion_tokens=200
    )
    score_budget = eval_cost_budget(max_cost_usd=0.01)(traj)
    assert score_budget.passed is True
