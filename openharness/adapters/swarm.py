"""
Swarm module for OpenHarness.
Provides core functionality for the swarm subsystem.
"""
from typing import Any, Dict, List
from openharness.core.types import Trajectory, Step, ToolCall


class OpenHarnessSwarmTracer:
    """Tracer for OpenAI Swarm agent handoffs and tool executions."""

    def __init__(self, name: str = "Swarm Handoff Run"):
        self.trajectory = Trajectory(name=name)

    def trace_response(self, swarm_response: Any) -> Trajectory:
        messages = getattr(swarm_response, "messages", [])
        agent = getattr(swarm_response, "agent", None)
        agent_name = getattr(agent, "name", "Agent") if agent else "Agent"

        for idx, msg in enumerate(messages, 1):
            content = msg.get("content") or ""
            tool_calls = []
            if "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    tool_calls.append(ToolCall(
                        name=func.get("name", "tool"),
                        args=func.get("arguments", {})
                    ))

            step = Step(
                step_index=idx,
                step_type="tool_call" if tool_calls else "agent_response",
                content=f"[{agent_name}] {content}",
                tool_calls=tool_calls
            )
            self.trajectory.steps.append(step)

        if messages:
            self.trajectory.final_output = str(messages[-1].get("content") or "")

        return self.trajectory
