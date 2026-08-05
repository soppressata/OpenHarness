from typing import Any, Dict, List, Optional
from openharness.core.types import Trajectory, Step, ToolCall


class OpenHarnessLangChainCallbackHandler:
    """Callback Handler for tracing LangChain and LangGraph agent runs into OpenHarness trajectories."""

    def __init__(self, name: str = "LangChain Agent Run"):
        self.name = name
        self.trajectory = Trajectory(name=name)
        self._current_step_idx = 0

    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs: Any) -> Any:
        self._current_step_idx += 1
        prompt_str = prompts[0] if prompts else ""
        if not self.trajectory.input_prompt:
            self.trajectory.input_prompt = prompt_str

        step = Step(
            step_index=self._current_step_idx,
            step_type="thought",
            content=f"LLM call started: {prompt_str[:100]}...",
            model=serialized.get("name") or serialized.get("id", ["llm"])[-1]
        )
        self.trajectory.steps.append(step)

    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs: Any) -> Any:
        self._current_step_idx += 1
        tool_name = serialized.get("name", "unknown_tool")
        tc = ToolCall(name=tool_name, args={"input": input_str})
        step = Step(
            step_index=self._current_step_idx,
            step_type="tool_call",
            content=f"Tool execution: {tool_name}",
            tool_calls=[tc]
        )
        self.trajectory.steps.append(step)

    def on_tool_end(self, output: str, **kwargs: Any) -> Any:
        if self.trajectory.steps:
            last_step = self.trajectory.steps[-1]
            if last_step.tool_calls:
                last_step.tool_calls[0].result = output

    def on_tool_error(self, error: Exception, **kwargs: Any) -> Any:
        if self.trajectory.steps:
            last_step = self.trajectory.steps[-1]
            if last_step.tool_calls:
                last_step.tool_calls[0].error = str(error)

    def on_chain_end(self, outputs: Dict[str, Any], **kwargs: Any) -> Any:
        final_ans = outputs.get("output") or outputs.get("result") or str(outputs)
        self.trajectory.final_output = str(final_ans)

    def get_trajectory(self) -> Trajectory:
        return self.trajectory
