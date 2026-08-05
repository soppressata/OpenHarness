import time
import uuid
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Represents a tool call invoked during agent execution."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    result: Optional[Any] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class Step(BaseModel):
    """Represents a single step or turn in an Agent execution trajectory."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    step_index: int = 0
    step_type: str = "thought"  # thought, tool_call, tool_result, agent_response, system
    content: str = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    model: Optional[str] = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Trajectory(BaseModel):
    """Complete multi-step execution trace of an agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "agent_run"
    input_prompt: str = ""
    steps: List[Step] = Field(default_factory=list)
    final_output: Optional[str] = None
    total_duration_ms: float = 0.0
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def get_tool_calls(self) -> List[ToolCall]:
        """Flatten and return all tool calls executed across all steps."""
        calls = []
        for step in self.steps:
            calls.extend(step.tool_calls)
        return calls

    def get_tool_names(self) -> List[str]:
        """Return list of all tool names executed in sequence."""
        return [tc.name for tc in self.get_tool_calls()]


class MetricScore(BaseModel):
    """Score output of an evaluator for a single metric."""
    name: str
    score: float  # Normalized 0.0 to 1.0 (or custom float)
    passed: bool
    reason: str = ""
    category: str = "assertion"  # assertion, trajectory, llm_judge, performance
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TestCase(BaseModel):
    """A benchmark test case used to evaluate an agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    input: Union[str, Dict[str, Any]]
    expected_output: Optional[Union[str, Dict[str, Any]]] = None
    expected_tools: Optional[List[str]] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    """Aggregate result of running evaluations on a single test case or run."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    run_id: str
    test_case_name: str
    trajectory: Optional[Trajectory] = None
    metrics: List[MetricScore] = Field(default_factory=list)
    passed: bool = True
    total_score: float = 1.0
    duration_ms: float = 0.0
    timestamp: float = Field(default_factory=time.time)
    metadata: Dict[str, Any] = Field(default_factory=dict)
