"""
Llamaindex module for OpenHarness.
Provides core functionality for the llamaindex subsystem.
"""
from typing import Any, Dict, Optional
from openharness.core.types import Trajectory, Step, ToolCall


class OpenHarnessLlamaIndexHandler:
    """Event handler for capturing LlamaIndex agent trajectories."""

    def __init__(self, name: str = "LlamaIndex Agent Run"):
        self.trajectory = Trajectory(name=name)
        self._step_idx = 0

    def on_event(self, event_type: str, payload: Optional[Dict[str, Any]] = None):
        self._step_idx += 1
        data = payload or {}

        if event_type == "llm":
            step = Step(
                step_index=self._step_idx,
                step_type="thought",
                content=str(data.get("messages") or data.get("prompt", ""))
            )
            self.trajectory.steps.append(step)
        elif event_type == "function_call":
            tc = ToolCall(name=data.get("name", "tool"), args=data.get("args", {}))
            step = Step(
                step_index=self._step_idx,
                step_type="tool_call",
                tool_calls=[tc]
            )
            self.trajectory.steps.append(step)

    def finish(self, final_output: str) -> Trajectory:
        self.trajectory.final_output = final_output
        return self.trajectory
