"""
Tests for AI Diagnostics Engine & Provider Adapters (Google, OpenAI, Anthropic).
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from openharness.diagnostics import (
    AIDiagnosticsEngine,
    FailedStepContext,
    DiagnosisReport,
    BaseProviderAdapter,
    GoogleAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    get_provider_adapter,
)


def test_provider_adapter_factory():
    google_p = get_provider_adapter("google")
    assert isinstance(google_p, GoogleAdapter)
    assert google_p.get_provider_name() == "google"

    openai_p = get_provider_adapter("openai", api_key="sk-test")
    assert isinstance(openai_p, OpenAIAdapter)
    assert openai_p.get_provider_name() == "openai"

    anthropic_p = get_provider_adapter("anthropic", api_key="sk-ant-test")
    assert isinstance(anthropic_p, AnthropicAdapter)
    assert anthropic_p.get_provider_name() == "anthropic"

    with pytest.raises(ValueError):
        get_provider_adapter("unsupported_provider")


def test_google_adapter_generate_completion():
    adapter = GoogleAdapter(api_key="fake-key")
    
    mock_response_data = {
        "candidates": [
            {
                "content": {
                    "parts": [{"text": json.dumps({
                        "error_type": "ImportError",
                        "root_cause": "Missing module numpy",
                        "summary": "numpy not installed",
                        "suggested_fix": "pip install numpy",
                        "confidence_score": 0.95
                    })}]
                }
            }
        ]
    }
    
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = adapter.generate_completion("Help with error", "System prompt")
        assert "ImportError" in res


def test_openai_adapter_generate_completion():
    adapter = OpenAIAdapter(api_key="fake-openai-key")

    mock_response_data = {
        "choices": [
            {
                "message": {
                    "content": json.dumps({
                        "error_type": "KeyError",
                        "root_cause": "Key 'id' missing from dict",
                        "summary": "KeyError in step",
                        "suggested_fix": "Use .get('id')",
                        "confidence_score": 0.9
                    })
                }
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = adapter.generate_completion("Help with key error")
        assert "KeyError" in res


def test_anthropic_adapter_generate_completion():
    adapter = AnthropicAdapter(api_key="fake-anthropic-key")

    mock_response_data = {
        "content": [
            {
                "text": json.dumps({
                    "error_type": "TypeError",
                    "root_cause": "Cannot concatenate str and int",
                    "summary": "TypeError encountered",
                    "suggested_fix": "Convert int to str",
                    "confidence_score": 0.92
                })
            }
        ]
    }

    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(mock_response_data).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = adapter.generate_completion("Help with type error", system_prompt="System context")
        assert "TypeError" in res


def test_capture_failure_from_exception():
    engine = AIDiagnosticsEngine(provider="google")
    
    try:
        x = 1 / 0
    except ZeroDivisionError as e:
        context = engine.capture_failure(
            step_id="step-101",
            step_name="Math Computation Step",
            exception=e,
            logs=["Initializing pipeline step", "Executing division task", "ZeroDivisionError: division by zero"],
        )

    assert context.step_id == "step-101"
    assert context.step_name == "Math Computation Step"
    assert "ZeroDivisionError" in context.error_message
    assert "ZeroDivisionError" in context.stack_trace
    assert len(context.logs) == 3


def test_diagnose_failure_heuristic_accuracy():
    engine = AIDiagnosticsEngine(provider="google")

    test_failures = [
        ("ImportError: No module named 'pydantic'", "ImportError"),
        ("KeyError: 'user_id'", "KeyError"),
        ("ZeroDivisionError: division by zero", "ZeroDivisionError"),
        ("TypeError: unsupported operand type(s) for +: 'int' and 'str'", "TypeError"),
        ("AttributeError: 'NoneType' object has no attribute 'get'", "AttributeError"),
        ("FileNotFoundError: [Errno 2] No such file or directory: 'config.json'", "FileNotFoundError"),
        ("TimeoutError: Step execution exceeded limit", "TimeoutError"),
        ("AssertionError: 2 != 5", "AssertionError"),
        ("ConnectionError: Failed to connect to host", "ConnectionError"),
        ("PermissionError: [Errno 13] Permission denied", "PermissionError"),
    ]

    correct_diagnoses = 0
    for error_str, expected_type in test_failures:
        context = engine.capture_failure(
            step_id="step-test",
            step_name="Test Step",
            logs=[error_str],
            stack_trace=error_str,
        )
        report = engine.diagnose_failure(context)
        if report.error_type == expected_type:
            correct_diagnoses += 1

    accuracy = correct_diagnoses / len(test_failures)
    assert accuracy >= 0.80, f"Root-cause accuracy was {accuracy * 100}%, expected >= 80%"


def test_format_report_for_ui():
    engine = AIDiagnosticsEngine(provider="openai")
    context = engine.capture_failure(
        step_id="step-ui-1",
        step_name="Database Migration Step",
        logs=["KeyError: 'db_port'"],
    )
    report = engine.diagnose_failure(context)
    ui_dict = engine.format_report_for_ui(report)

    assert ui_dict["step_id"] == "step-ui-1"
    assert ui_dict["provider"] == "OPENAI"
    assert "Database Migration Step" in ui_dict["title"]
    assert "KeyError" in ui_dict["error_type"]
    assert "confidence" in ui_dict
    assert "suggested_fix" in ui_dict
