import pytest
from unittest.mock import MagicMock, patch
from openharness import generate_synthetic_dataset
from openharness.providers import BaseProvider, ProviderResponse


class MockGenProvider(BaseProvider):
    def generate(self, prompt: str, **kwargs):
        json_content = '[{"name": "Refund Test", "input": "Refund #1", "expected_output": "Refunded", "expected_tools": ["refund"]}]'
        return ProviderResponse(content=json_content, model="mock-gen")

    async def agenerate(self, prompt: str, **kwargs):
        return self.generate(prompt, **kwargs)

    def check_connection(self):
        return True


def test_generate_synthetic_dataset():
    prov = MockGenProvider()
    ds = generate_synthetic_dataset(seed_prompt="E-commerce support", n_cases=1, provider=prov)
    assert len(ds.cases) == 1
    assert ds.cases[0].name == "Refund Test"
    assert ds.cases[0].expected_tools == ["refund"]


def test_generate_synthetic_dataset_fallback():
    failing_prov = MagicMock()
    failing_prov.generate.side_effect = RuntimeError("Generation failed")
    ds = generate_synthetic_dataset(seed_prompt="Fallback domain", n_cases=3, provider=failing_prov)
    assert len(ds.cases) == 3
    assert ds.cases[0].metadata.get("fallback") is True
