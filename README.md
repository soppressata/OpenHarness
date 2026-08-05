# ⚡ OpenHarness: Next-Gen Agentic Harness Evaluator

> **Zero-Cost, Local-First, Open-Source Evaluation Harness for AI Agents & Multi-Step Workflows.**  
> An open-source alternative to Braintrust, LangSmith, and LangFuse—built for developers who want fast, privacy-first, zero-fee evaluations.

---

## 🌟 Key Features

- 💰 **Zero Cost & Local First**: Evaluate using local LLMs (**Ollama**, **vLLM**, **llama.cpp**) and embedded zero-config SQLite storage (`.openharness/evals.db`). No mandatory cloud subscriptions or per-eval fees.
- 🔄 **Agentic Trajectory Evals**: Built specifically for multi-turn agents. Track tool call precision & recall, loop detection, goal completion, step efficiency, and execution timelines.
- 🐍 **Python SDK & Pytest Plugin**: First-class Python package (`pip install openharness`) with clean decorators (`@harness`, `eval_case`) and native `pytest` integration.
- 📘 **TypeScript / Node SDK**: First-class NPM package (`@openharness/core`) for JavaScript/Node agentic stacks.
- 🎨 **Local Dashboard (`harness ui`)**: Single-command embedded web dashboard featuring trajectory step visualizers, pass rate heatmaps, and metric breakdowns.
- 🌐 **Multi-Provider LLM Judge**: Use local models (`ollama/llama3.1`, `vllm/qwen2.5-coder`) or cloud APIs (`openai/gpt-4o`, `gemini`) for LLM-as-a-Judge and pairwise arena evaluations.

---

## 🚀 Quickstart (Python)

### 1. Installation
```bash
pip install openharness
```

### 2. Write an Evaluation Case (`harness_example.py`)
```python
from openharness import (
    Harness,
    assert_tool_called,
    assert_tool_not_called,
    assert_exact_match,
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection
)

def my_support_agent(user_query: str):
    # Your agent execution returning string or Trajectory object
    return "Order ORD-123 refunded."

def run_eval():
    h = Harness(name="Customer Support Suite")

    h.run_case(
        test_case_name="Refund Order Case",
        agent_fn=my_support_agent,
        input_data="Refund order ORD-123",
        evaluators=[
            assert_exact_match("Order ORD-123 refunded."),
            eval_goal_completion(),
            eval_tool_precision(),
            eval_loop_detection()
        ]
    )

    h.save()

if __name__ == "__main__":
    run_eval()
```

### 3. View Reports & Dashboard
```bash
# Terminal summary report
harness report

# Launch local visual UI dashboard at http://localhost:8501
harness ui
```

---

## 🤖 GitHub Actions CI

Wire OpenHarness into your GitHub Actions pipeline in one command:

```bash
harness init --ci github
```

This scaffolds `.github/workflows/eval.yml` with a workflow that installs
OpenHarness, runs your eval suite, caches pip & eval state, and uploads the
generated `report.html` as a downloadable build artifact (retained 14 days).
Commit the file and push — evals run on every push and pull request.

---

## 📘 Quickstart (TypeScript / Node)

```bash
npm install @openharness/core
```

```typescript
import { Harness, assertToolCalled, assertExactMatch } from "@openharness/core";

const harness = new Harness("React Agent Benchmark");

await harness.runCase(
  "Generate Component",
  async (prompt) => {
    return {
      inputPrompt: prompt,
      steps: [{
        stepIndex: 1,
        stepType: "tool_call",
        content: "Writing component...",
        toolCalls: [{ name: "write_file", args: { path: "src/Button.tsx" } }]
      }],
      finalOutput: "Component created."
    };
  },
  "Create Button.tsx",
  [
    assertToolCalled("write_file", { path: "src/Button.tsx" }),
    assertExactMatch("Component created.")
  ]
);
```

---

## 🏗️ Architecture & Storage

- **Trace Store**: Embedded SQLite database automatically created at `.openharness/evals.db`.
- **CLI Commands**:
  - `harness run`: Run evaluation suite.
  - `harness report`: Print terminal summary of past runs & scorecards.
  - `harness ui`: Start the FastAPI web dashboard.
  - `harness init`: Initialize a boilerplate evaluation script.
  - `harness init --ci github`: Scaffold a GitHub Actions CI workflow template.

---

## 🧪 Testing

```bash
pytest -v
```

---

## 📄 License
MIT License. Open-source for everyone.
