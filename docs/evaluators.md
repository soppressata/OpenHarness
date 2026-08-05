# OpenHarness Evaluators Reference

OpenHarness provides three tiers of evaluation tools:

## 1. Assertion Evaluators (`openharness.evaluators.assertions`)

- `assert_tool_called(tool_name, kwargs=None, order=None)`: Verifies if a specific tool was invoked with matching parameters and position.
- `assert_tool_not_called(tool_name)`: Ensures forbidden or unsafe tools are omitted.
- `assert_exact_match(expected)`: String equality match.
- `assert_regex(pattern)`: Regular expression pattern match on agent output.
- `assert_json_schema(schema)`: Validates final output adheres to JSON schema keys.
- `assert_custom(name, check_fn)`: User-defined custom logic assertion.

---

## 2. Trajectory & Agentic Metrics (`openharness.evaluators.trajectory` & `advanced`)

- `eval_goal_completion()`: Verifies agent provided non-empty answer without unhandled tool crashes.
- `eval_tool_precision()`: Ratio of successful tool calls vs errored tool calls.
- `eval_loop_detection(max_repeats=2)`: Flags agents stuck in repeating tool execution loops.
- `eval_step_efficiency(max_expected_steps=10)`: Evaluates trajectory step count against step budget.
- `eval_hallucinated_tools(available_tools)`: Detects attempts to call non-existent tools.
- `eval_argument_schema(tool_schemas)`: Validates tool call parameters against JSON schema definitions.
- `eval_retry_overflow(max_retries=2)`: Flags tools executed repeatedly due to internal exceptions.

---

## 3. Semantic & LLM-as-a-Judge (`openharness.evaluators.semantic` & `llm_judge`)

- `eval_semantic_similarity(expected, threshold=0.75)`: Cosine similarity between agent output and ground truth.
- `eval_factuality_and_hallucination(context_documents)`: Reference-grounded context factuality (RAG eval).
- `eval_safety_and_jailbreak(forbidden_keywords=None)`: Red-teaming and prompt injection guardrail assertion.
- `eval_cost_budget(max_cost_usd=0.05)`: Monetary execution cost limit assertion.
- `llm_judge(rubric, model="ollama/llama3.1")`: Custom rubric judging using local or cloud LLMs.
- `pairwise_arena_judge(rubric, model="ollama/llama3.1")`: Head-to-head arena judging comparing two agent outputs.
