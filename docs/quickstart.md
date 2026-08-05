# OpenHarness Quickstart Guide

Welcome to **OpenHarness**, the zero-cost, local-first evaluation harness for AI Agents and LLM workflows.

## Installation

```bash
pip install openharness
```

Or for Node.js / TypeScript:

```bash
npm install @openharness/core
```

---

## 1. Defining Your First Agent Evaluation

Create `eval_demo.py`:

```python
from openharness import (
    Harness,
    assert_tool_called,
    assert_exact_match,
    eval_goal_completion,
    eval_tool_precision,
    eval_loop_detection
)

def my_agent(prompt: str):
    # Your agent code returning string or Trajectory
    return "Order ORD-999 refunded successfully."

def main():
    h = Harness("E-commerce Agent Suite")

    h.run_case(
        test_case_name="Refund Order #999",
        agent_fn=my_agent,
        input_data="Issue refund for ORD-999",
        evaluators=[
            assert_exact_match("Order ORD-999 refunded successfully."),
            eval_goal_completion(),
            eval_tool_precision(),
            eval_loop_detection()
        ]
    )

    run_id = h.save()
    print(f"Evaluation complete! Run ID: {run_id}")

if __name__ == "__main__":
    main()
```

---

## 2. Viewing Results & Visualizations

Run evaluation report in terminal:

```bash
harness report
```

Render ASCII Gantt Waterfall chart for terminal:

```bash
harness viz --run-id <RUN_ID>
```

Launch the interactive local dashboard at `http://localhost:8501`:

```bash
harness ui
```

Export JUnit XML or HTML report for CI/CD:

```bash
harness export --run-id <RUN_ID> --format html --out report.html
```
