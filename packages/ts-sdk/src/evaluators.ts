import { MetricScore, Trajectory, Evaluator } from "./types";

export function assertExactMatch(expected: string): Evaluator {
  return (target: string | Trajectory): MetricScore => {
    const actual = typeof target === "string" ? target : target.finalOutput || "";
    const passed = actual.trim() === expected.trim();
    return {
      name: "exact_match",
      score: passed ? 1.0 : 0.0,
      passed,
      reason: passed ? "Output matches expected string." : `Expected "${expected}", got "${actual}"`,
      category: "assertion"
    };
  };
}

export function assertToolCalled(toolName: string, expectedKwargs?: Record<string, any>): Evaluator {
  return (target: string | Trajectory): MetricScore => {
    if (typeof target === "string") {
      return {
        name: `tool_called:${toolName}`,
        score: 0,
        passed: false,
        reason: "Target is a plain string, not a multi-step Trajectory.",
        category: "assertion"
      };
    }

    const allToolCalls = target.steps.flatMap(s => s.toolCalls || []);
    const matching = allToolCalls.filter(tc => tc.name === toolName);

    if (matching.length === 0) {
      return {
        name: `tool_called:${toolName}`,
        score: 0,
        passed: false,
        reason: `Tool "${toolName}" was never executed.`,
        category: "assertion"
      };
    }

    if (expectedKwargs) {
      const matchArgs = matching.some(tc => 
        Object.entries(expectedKwargs).every(([k, v]) => tc.args[k] === v)
      );
      if (!matchArgs) {
        return {
          name: `tool_called:${toolName}`,
          score: 0,
          passed: false,
          reason: `Tool "${toolName}" was called but arguments did not match ${JSON.stringify(expectedKwargs)}.`,
          category: "assertion"
        };
      }
    }

    return {
      name: `tool_called:${toolName}`,
      score: 1.0,
      passed: true,
      reason: `Tool "${toolName}" called with expected criteria.`,
      category: "assertion"
    };
  };
}
