"""
Synthetic module for OpenHarness.
Provides core functionality for the synthetic subsystem.
"""
import json
import re
from typing import List, Optional, Union
from openharness.core.dataset import Dataset
from openharness.core.types import TestCase
from openharness.providers import get_provider, BaseProvider


SYNTHETIC_GEN_PROMPT = """
You are an expert AI Benchmark Engineer creating synthetic evaluation test cases for AI agents.

[DOMAIN / SEED DESCRIPTION]:
{seed_prompt}

Generate {n_cases} diverse, high-quality test cases for evaluating an AI Agent in this domain.
Each test case should have:
- "name": Short test case name
- "input": User query or prompt given to the agent
- "expected_output": Ground truth expected answer or action summary
- "expected_tools": List of tool names that the agent should ideally call

Respond ONLY with a JSON array of objects:
[
  {{
    "name": "Refund Request",
    "input": "Can I return order #123?",
    "expected_output": "Refund issued.",
    "expected_tools": ["lookup_order", "issue_refund"]
  }}
]
"""


def generate_synthetic_dataset(
    seed_prompt: str,
    n_cases: int = 5,
    model: str = "ollama/llama3.1",
    provider: Optional[BaseProvider] = None,
    dataset_name: Optional[str] = None
) -> Dataset:
    """Generate a synthetic evaluation dataset using local or cloud LLMs."""
    llm_provider = provider or get_provider(model)

    prompt = SYNTHETIC_GEN_PROMPT.format(
        seed_prompt=seed_prompt,
        n_cases=n_cases
    )

    try:
        response = llm_provider.generate(prompt=prompt, temperature=0.7)
        content = response.content.strip()

        # Extract JSON array
        json_match = re.search(r"\[.*\]", content, re.DOTALL)
        if json_match:
            content = json_match.group(0)

        raw_cases = json.loads(content)
        cases = []
        for i, item in enumerate(raw_cases):
            cases.append(TestCase(
                name=item.get("name", f"synthetic_case_{i+1}"),
                input=item.get("input", ""),
                expected_output=item.get("expected_output"),
                expected_tools=item.get("expected_tools"),
                metadata={"synthetic": True, "generated_by": response.model}
            ))

        return Dataset(name=dataset_name or f"synthetic_{n_cases}_cases", cases=cases)
    except Exception as e:
        # Fallback dataset if LLM generation is unavailable
        fallback_cases = [
            TestCase(
                name=f"fallback_synthetic_{i+1}",
                input=f"Synthetic test prompt #{i+1} for domain: {seed_prompt[:30]}",
                expected_output="Sample expected output",
                metadata={"fallback": True, "error": str(e)}
            )
            for i in range(n_cases)
        ]
        return Dataset(name=dataset_name or "synthetic_fallback", cases=fallback_cases)
