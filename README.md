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

## 🚀 Getting Started (Python)

### 1. Installation

You can install OpenHarness directly from PyPI or set up a local clone for development:

#### Option A: Install via PyPI (User Mode)
```bash
pip install openharness
```

#### Option B: Local Setup (Developer Mode)
If you cloned the repository or are developing/testing locally:
```bash
# Clone the repository (if not already done)
git clone https://github.com/soppressata/OpenHarness.git
cd OpenHarness

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install in editable mode with development dependencies
pip install -e .[dev]
```

---

### 2. Configuration & Environment Variables

OpenHarness runs **entirely locally by default** with a zero-config SQLite database (`.openharness/evals.db`). Basic assertions (exact match, regex, tool-call tracking, goal completion, and loop detection) require **no external API keys**.

However, if you wish to use advanced evaluators like **LLM-as-a-Judge (`llm_judge`)**, **Pairwise Arena Judges**, or **Synthetic Dataset Generation**, you will need to configure an LLM provider.

#### Step 2.1: Bootstrap your Project
Initialize OpenHarness in your project root to generate the sample evaluation script `harness_example.py` and a `.env.example` template:
```bash
harness init
```

#### Step 2.2: Set Up Environment Variables
Create your local `.env` file:
```bash
cp .env.example .env
```

OpenHarness reads the following environment variables from the environment:
- `OPENAI_API_KEY`: Required for OpenAI models (e.g. `gpt-4o-mini`).
- `OPENAI_BASE_URL`: Optional custom base URL for OpenAI-compatible proxies/routers (defaults to `https://api.openai.com/v1`).
- `OPENHARNESS_DB_URL`: Optional PostgreSQL connection string (e.g., `postgresql://user:pass@host:5432/db`) to use Postgres storage instead of local SQLite.

> [!NOTE]
> For **Local Ollama** (e.g., `ollama/llama3.1`), ensure your Ollama instance is running locally on port `11434` and that you have pulled the model (`ollama pull llama3.1`). No environment variables are required for Ollama.

---

### 3. Walkthrough: Your First Successful Run

Let's run a simple evaluation check on an agent function.

#### Step 3.1: Write the Evaluation Script (`harness_example.py`)
Ensure your `harness_example.py` file looks like this:

```python
from openharness import eval_case, assert_exact_match, eval_goal_completion

# 1. Define your agent function
def my_simple_agent(user_query: str) -> str:
    # Simulating agent processing
    return "Refund processed for order #12345"

# 2. Run the evaluation case
def test_refund():
    result = eval_case(
        name="Refund Agent Test",
        agent_fn=my_simple_agent,
        input_data="Issue refund for order #12345",
        evaluators=[
            assert_exact_match("Refund processed for order #12345"),
            eval_goal_completion()
        ]
    )
    print(f"Eval Result: Passed={result.passed}, Score={result.total_score}")

if __name__ == "__main__":
    test_refund()
```

#### Step 3.2: Run the Evaluation
Execute the script using Python:
```bash
python3 harness_example.py
```

**Expected Console Output:**
```text
Eval Result: Passed=True, Score=1.0
```

---

### 4. Viewing Reports & Visualizations

OpenHarness provides built-in tools to inspect evaluation metrics and trajectories in your terminal or in a browser.

#### Terminal Summary Report
To view a breakdown of all runs and passing/failing criteria, run:
```bash
harness report
```

**Example Output:**
```text
=================================================================
       OPENHARNESS EVALUATION SUMMARY REPORT       
=================================================================
Run ID: fe6cbfaa | Name: EvalCase: Refund Agent Test | Pass Rate: 100.0% (1/1) | Duration: 0.1ms
  ✅ Case: Refund Agent Test (Score: 1.00, 0.1ms)
      └─ ✔ [assertion] exact_match: Output matches expected string.
      └─ ✔ [trajectory] goal_completion: Goal successfully completed without tool errors.
-----------------------------------------------------------------
```

#### ASCII Scorecard & Quality Visualizations
Render ASCII scorecards and quality-vs-latency Pareto frontiers for your latest run:
```bash
harness viz
```

**Example Output:**
```text
=================================================================
📊 VISUALIZATIONS FOR RUN: EvalCase: Refund Agent Test (fe6cbfaa)
=================================================================
📋 EVALUATION SCORECARD MATRIX
=================================================================
TEST CASE                      | SCORE   | STATUS   | METRICS PASSED
-----------------------------------------------------------------
Refund Agent Test              |    1.00 | PASS ✅   | 2/2
=================================================================

🎯 QUALITY VS LATENCY PARETO MATRIX
======================================================================
TEST CASE                    | QUALITY  | LATENCY   | PARETO EFFICIENCY
----------------------------------------------------------------------
Refund Agent Test            |     1.00 | 0.1ms     | OPTIMAL (High Quality)
======================================================================
```

#### Launch the Web Dashboard
Open the interactive local web UI to inspect step-by-step agent trajectories:
```bash
harness ui
```
Open `http://localhost:8501` in your browser.

#### Retention & Cleanup
Every run appends full results, metric scores, and step-by-step trajectories to the
local database. To keep `.openharness/evals.db` from growing unboundedly, prune old
runs by age or delete a single run by ID:

```bash
# Preview exactly what would be deleted (no changes)
harness prune --older-than 30 --dry-run

# Delete all runs older than 30 days
harness prune --older-than 30

# Delete a single run
harness prune --run-id <RUN_ID>
```

Pruning fully cascades (metric scores, results, and trajectories are removed together),
so no orphaned rows are left behind.

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

- **Trace Store**:
  - **Local/Default SQLite**: An embedded SQLite database is automatically created at `.openharness/evals.db`. It is configured in **WAL (Write-Ahead Logging) mode** with a busy timeout of 5 seconds, ensuring high concurrency and safe parallel execution across multi-threaded or multi-process runner tasks (e.g. parallelized CI/CD pipelines).
  - **Remote PostgreSQL**: For team collaboration and shared visibility across developers and automated CI/CD pipelines, you can connect to a shared PostgreSQL database. Set the `OPENHARNESS_DB_URL` environment variable to a valid PostgreSQL connection string (e.g. `postgresql://username:password@localhost:5432/openharness_db`). Make sure you have a PostgreSQL client installed (`pip install psycopg2-binary`).
- **CLI Commands**:
  - `harness run`: Run evaluation suite.
  - `harness report`: Print terminal summary of past runs & scorecards.
  - `harness ui`: Start the FastAPI web dashboard.
  - `harness init`: Initialize a boilerplate evaluation script.
  - `harness init --ci github`: Scaffold a GitHub Actions CI workflow template.
  - `harness prune`: Prune old evaluation runs (`--older-than <days>` or `--run-id`) to reclaim database space.

---

## 🧪 Testing

```bash
pytest -v
```

---

## 📄 License
MIT License. Open-source for everyone.
