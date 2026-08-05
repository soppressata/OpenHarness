"""Generate CI/CD workflow templates for running OpenHarness evals.

This module scaffolds provider-specific CI pipeline files (currently
GitHub Actions) that install OpenHarness, run a Python eval suite, cache
model/dependency state, and upload the generated HTML report as an artifact.
"""

import os
from typing import Optional

GITHUB_ACTIONS_TEMPLATE = """\
name: OpenHarness Eval

on:
  push:
  pull_request:

jobs:
  eval:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'

      - name: Cache pip dependencies
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-${{ hashFiles('**/pyproject.toml') }}
          restore-keys: |
            ${{ runner.os }}-pip-

      - name: Cache OpenHarness evaluation database
        uses: actions/cache@v4
        with:
          path: .openharness
          key: ${{ runner.os }}-openharness-${{ github.sha }}
          restore-keys: |
            ${{ runner.os }}-openharness-

      - name: Install OpenHarness
        run: pip install .[dev]

      - name: Run evaluation suite
        run: harness run

      - name: Upload HTML evaluation report
        uses: actions/upload-artifact@v4
        with:
          name: openharness-report
          path: report.html
          retention-days: 14
"""


def generate_github_actions_yaml(
    path: str = ".github/workflows/eval.yml",
) -> Optional[str]:
    """Scaffold a GitHub Actions workflow file for OpenHarness evals.

    Args:
        path: Destination file path for the generated workflow.

    Returns:
        The absolute path written to, or None if the file already exists.
    """
    workflow_dir = os.path.dirname(path)
    if workflow_dir:
        os.makedirs(workflow_dir, exist_ok=True)
    if os.path.exists(path):
        return None
    with open(path, "w", encoding="utf-8") as f:
        f.write(GITHUB_ACTIONS_TEMPLATE)
    return os.path.abspath(path)


def generate_ci_template(provider: str) -> str:
    """Return the CI workflow template body for a given provider.

    Args:
        provider: Supported CI provider ("github").

    Returns:
        The YAML template content.

    Raises:
        ValueError: If the provider is not supported.
    """
    normalized = provider.lower()
    if normalized == "github":
        return GITHUB_ACTIONS_TEMPLATE
    raise ValueError(f"Unsupported CI provider: {provider!r}")