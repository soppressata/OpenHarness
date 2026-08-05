from typing import Any, Dict, List
from openharness.core.types import Trajectory, Step, ToolCall


class OpenHarnessAutoGenTracer:
    """Tracer for AutoGen multi-agent conversations."""

    def __init__(self, name: str = "AutoGen Multi-Agent Run"):
        self.trajectory = Trajectory(name=name)

    def trace_messages(self, messages: List[Dict[str, Any]]) -> Trajectory:
        for idx, msg in enumerate(messages, 1):
            sender = msg.get("name") or msg.get("role", "agent")
            content = msg.get("content", "")
            
            tool_calls = []
            if "function_call" in msg:
                fc = msg["function_call"]
                tool_calls.append(ToolCall(name=fc.get("name", "func"), args=fc.get("arguments", {})))

            step = Step(
                step_index=idx,
                step_type="agent_response" if not tool_calls else "tool_call",
                content=f"[{sender}] {content}",
                tool_calls=tool_calls
            )
            self.trajectory.steps.append(step)

        if messages:
            self.trajectory.final_output = messages[-1].get("content", "")
        return self.trajectory
