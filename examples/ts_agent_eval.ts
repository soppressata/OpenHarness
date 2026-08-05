import { Harness, assertExactMatch, assertToolCalled, Trajectory } from "../packages/ts-sdk/dist";

async function runTsBenchmark() {
  console.log("🚀 Running TypeScript OpenHarness Benchmark...\n");

  const harness = new Harness("Code Assistant Agent Benchmark");

  const agentResult = await harness.runCase(
    "React Component Generator",
    async (inputPrompt: string): Promise<Trajectory> => {
      return {
        inputPrompt,
        steps: [
          {
            stepIndex: 1,
            stepType: "tool_call",
            content: "Writing component file...",
            toolCalls: [{ name: "write_file", args: { path: "src/Button.tsx" } }]
          }
        ],
        finalOutput: "Component Button.tsx generated."
      };
    },
    "Create a primary button component in src/Button.tsx",
    [
      assertToolCalled("write_file", { path: "src/Button.tsx" }),
      assertExactMatch("Component Button.tsx generated.")
    ]
  );

  console.log(`Test Case: ${agentResult.testCaseName}`);
  console.log(`Passed: ${agentResult.passed}, Score: ${agentResult.totalScore}`);
}

runTsBenchmark();
