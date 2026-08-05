"""
OpenHarness: Open-Source Agentic Harness Evaluator
Zero-cost, local-first evaluation harness for AI Agents and LLM workflows.
"""

__version__ = "0.1.0"

from openharness.core.types import (
    ToolCall,
    Step,
    Trajectory,
    MetricScore,
    EvaluationResult,
    TestCase
)
from openharness.core.harness import Harness, harness, eval_case
from openharness.core.dataset import Dataset, eval_dataset
from openharness.core.sweeps import run_determinism_sweep, SweepSummary
from openharness.core.analytics import calculate_trajectory_cost, calculate_latency_breakdown
from openharness.core.exporters import export_to_json, export_to_html, export_to_junit_xml
from openharness.core.visualizations import (
    render_ascii_waterfall,
    render_ascii_scorecard,
    render_ascii_quality_radar,
    render_svg_waterfall,
    render_pairwise_diff_html
)
from openharness.core.synthetic import generate_synthetic_dataset
from openharness.core.experiment import run_ab_experiment, ExperimentResult

from openharness.evaluators.assertions import (
    assert_tool_called,
    assert_tool_not_called,
    assert_exact_match,
    assert_regex,
    assert_json_schema,
    assert_custom
)
from openharness.evaluators.trajectory import (
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection,
    eval_step_efficiency
)
from openharness.evaluators.advanced import (
    eval_hallucinated_tools,
    eval_argument_schema,
    eval_retry_overflow
)
from openharness.evaluators.semantic import (
    eval_semantic_similarity,
    eval_factuality_and_hallucination,
    eval_safety_and_jailbreak,
    eval_cost_budget
)
from openharness.evaluators.quality import (
    eval_code_quality,
    eval_reasoning_depth,
    eval_quality_pareto_index
)
from openharness.evaluators.llm_judge import llm_judge, pairwise_arena_judge

from openharness.adapters.langchain import OpenHarnessLangChainCallbackHandler
from openharness.adapters.llamaindex import OpenHarnessLlamaIndexHandler
from openharness.adapters.autogen import OpenHarnessAutoGenTracer
from openharness.adapters.swarm import OpenHarnessSwarmTracer

__all__ = [
    "Harness",
    "harness",
    "eval_case",
    "Dataset",
    "eval_dataset",
    "run_determinism_sweep",
    "SweepSummary",
    "calculate_trajectory_cost",
    "calculate_latency_breakdown",
    "export_to_json",
    "export_to_html",
    "export_to_junit_xml",
    "render_ascii_waterfall",
    "render_ascii_scorecard",
    "render_ascii_quality_radar",
    "render_svg_waterfall",
    "render_pairwise_diff_html",
    "generate_synthetic_dataset",
    "run_ab_experiment",
    "ExperimentResult",
    "ToolCall",
    "Step",
    "Trajectory",
    "MetricScore",
    "EvaluationResult",
    "TestCase",
    "assert_tool_called",
    "assert_tool_not_called",
    "assert_exact_match",
    "assert_regex",
    "assert_json_schema",
    "assert_custom",
    "eval_goal_completion",
    "eval_tool_precision",
    "eval_loop_detection",
    "eval_step_efficiency",
    "eval_hallucinated_tools",
    "eval_argument_schema",
    "eval_retry_overflow",
    "eval_semantic_similarity",
    "eval_factuality_and_hallucination",
    "eval_safety_and_jailbreak",
    "eval_cost_budget",
    "eval_code_quality",
    "eval_reasoning_depth",
    "eval_quality_pareto_index",
    "llm_judge",
    "pairwise_arena_judge",
    "OpenHarnessLangChainCallbackHandler",
    "OpenHarnessLlamaIndexHandler",
    "OpenHarnessAutoGenTracer",
    "OpenHarnessSwarmTracer"
]
