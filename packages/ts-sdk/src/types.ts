export interface ToolCall {
  id?: string;
  name: string;
  args: Record<string, any>;
  result?: any;
  error?: string;
  durationMs?: number;
}

export interface Step {
  id?: string;
  stepIndex: number;
  stepType: "thought" | "tool_call" | "tool_result" | "agent_response" | "system";
  content: string;
  toolCalls?: ToolCall[];
  model?: string;
  durationMs?: number;
}

export interface Trajectory {
  id?: string;
  name?: string;
  inputPrompt: string;
  steps: Step[];
  finalOutput?: string;
  totalDurationMs?: number;
}

export interface MetricScore {
  name: string;
  score: number;
  passed: boolean;
  reason: string;
  category?: string;
}

export type Evaluator = (target: string | Trajectory) => MetricScore | Promise<MetricScore>;

export interface TestCase {
  id?: string;
  name: string;
  input: any;
  expectedOutput?: any;
}

export interface EvaluationResult {
  id: string;
  runId: string;
  testCaseName: string;
  trajectory?: Trajectory;
  metrics: MetricScore[];
  passed: boolean;
  totalScore: number;
  durationMs: number;
}
