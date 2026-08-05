import { EvaluationResult, MetricScore, TestCase, Trajectory, Evaluator } from "./types";
import { assertExactMatch, assertToolCalled } from "./evaluators";

export class Harness {
  private runId: string;
  private name: string;
  private results: EvaluationResult[] = [];

  constructor(name: string = "TS Evaluation Run") {
    this.name = name;
    this.runId = Math.random().toString(36).substring(2, 10);
  }

  async runCase(
    name: string,
    agentFn: (input: any) => Promise<string | Trajectory> | string | Trajectory,
    inputData: any,
    evaluators: Evaluator[]
  ): Promise<EvaluationResult> {
    const startTime = Date.now();
    let trajectory: Trajectory | undefined;
    let output = "";
    let errorMsg: string | undefined;

    try {
      const raw = await agentFn(inputData);
      if (typeof raw === "string") {
        output = raw;
        trajectory = { inputPrompt: String(inputData), steps: [], finalOutput: output };
      } else {
        trajectory = raw;
        output = raw.finalOutput || "";
      }
    } catch (e: any) {
      errorMsg = e.message || String(e);
    }

    const metrics: MetricScore[] = [];
    const target = trajectory || output;

    for (const ev of evaluators) {
      try {
        const score = await ev(target);
        metrics.push(score);
      } catch (err: any) {
        metrics.push({
          name: "evaluator_error",
          score: 0,
          passed: false,
          reason: err.message || String(err),
          category: "assertion"
        });
      }
    }

    const passed = metrics.every(m => m.passed) && !errorMsg;
    const totalScore = metrics.length > 0 ? metrics.reduce((a, b) => a + b.score, 0) / metrics.length : 1.0;
    const durationMs = Date.now() - startTime;

    const result: EvaluationResult = {
      id: Math.random().toString(36).substring(2, 10),
      runId: this.runId,
      testCaseName: name,
      trajectory,
      metrics,
      passed,
      totalScore,
      durationMs
    };

    this.results.push(result);
    return result;
  }

  getResults(): EvaluationResult[] {
    return this.results;
  }
}

export { assertExactMatch, assertToolCalled };
export * from "./types";
