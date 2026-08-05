"""
AI Pipeline Generator module for OpenHarness.
Generates autonomous deployment execution plans and foundational architecture documentation.
"""

import json
import re
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field


class PipelineStage(BaseModel):
    """A stage in the generated execution plan."""
    name: str = Field(..., description="Stage name")
    action: str = Field(..., description="Action to perform in this stage")
    commands: List[str] = Field(default_factory=list, description="CLI/sandbox commands for execution")
    timeout_seconds: int = Field(default=300, description="Stage timeout in seconds")


class ArchitectureDoc(BaseModel):
    """Foundational architecture documentation for the generated pipeline."""
    title: str = Field(..., description="Architecture document title")
    target_environment: str = Field(..., description="Target cloud or runtime environment")
    summary: str = Field(..., description="High-level architectural summary")
    self_healing_policy: str = Field(..., description="Autonomous self-healing rules and policies")
    monitoring_strategy: str = Field(..., description="Continuous telemetry and monitoring strategy")
    constraints: List[str] = Field(default_factory=list, description="Extracted constraints (uptime, cost, etc.)")


class PipelinePlan(BaseModel):
    """Functional pipeline execution plan and architecture documentation."""
    prompt: str = Field(..., description="Input natural language prompt")
    pipeline_name: str = Field(..., description="Generated name of the pipeline")
    target_environment: str = Field(..., description="Primary deployment target")
    stages: List[PipelineStage] = Field(default_factory=list, description="Execution plan stages")
    architecture_doc: ArchitectureDoc = Field(..., description="Foundational architecture documentation")

    def to_dict(self) -> Dict[str, Any]:
        """Convert pipeline plan model to dictionary format."""
        return self.model_dump()

    def to_json(self, indent: int = 2) -> str:
        """Serialize pipeline plan to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)


# Alias for backward compatibility / QA test suite imports
AIPipelineResult = PipelinePlan


class AIPipelineGenerator:
    """Engine for generating AI-native deployment pipelines from declarative prompts."""

    def __init__(self, default_environment: str = "AWS Container Engine"):
        self.default_environment = default_environment

    def _extract_environment(self, prompt: str) -> str:
        prompt_lower = prompt.lower()
        if "aws" in prompt_lower:
            return "AWS (Amazon Web Services)"
        elif "gcp" in prompt_lower or "google cloud" in prompt_lower:
            return "GCP (Google Cloud Platform)"
        elif "azure" in prompt_lower:
            return "Microsoft Azure"
        elif "k8s" in prompt_lower or "kubernetes" in prompt_lower:
            return "Kubernetes Cluster"
        elif "docker" in prompt_lower:
            return "Docker Container Runtime"
        return self.default_environment

    def _extract_constraints(self, prompt: str) -> List[str]:
        constraints = []
        uptime_match = re.search(r"(\d+(\.\d+)?%)\s*(uptime|availability)", prompt, re.IGNORECASE)
        if uptime_match:
            constraints.append(f"Availability SLA: {uptime_match.group(1)} uptime")

        cost_match = re.search(r"(\$?\d+([.,]\d+)?)\s*(/|\s*per\s*)?\s*(mo|month)", prompt, re.IGNORECASE)
        if cost_match:
            val = cost_match.group(1)
            if not val.startswith("$"):
                val = f"${val}"
            constraints.append(f"Budget Limit: {val}/month")

        if not constraints:
            constraints.append("Default SLA: 99.9% uptime")
            constraints.append("Default Budget: Optimal cost allocation")
        return constraints

    def generate(self, prompt: str) -> PipelinePlan:
        """
        Generate a functional pipeline execution plan and architecture documentation from a prompt.

        Args:
            prompt: Natural language user prompt specifying desired deployment state.

        Returns:
            PipelinePlan containing structured execution stages and architecture documentation.
        """
        target_env = self._extract_environment(prompt)
        constraints = self._extract_constraints(prompt)

        stages = [
            PipelineStage(
                name="validate_and_build",
                action="Validate application code and build immutable container artifact",
                commands=[
                    "echo 'Validating source code and dependencies...'",
                    "docker build -t app:${GIT_COMMIT:-latest} ."
                ],
                timeout_seconds=300
            ),
            PipelineStage(
                name="test_and_evaluate",
                action="Run test suite and agentic trajectory evaluation harness",
                commands=[
                    "pytest tests/",
                    "openharness eval --suite regression"
                ],
                timeout_seconds=600
            ),
            PipelineStage(
                name="security_and_compliance",
                action="Scan for vulnerabilities and verify policy compliance",
                commands=[
                    "openharness policy-check --strict",
                    "trivy image app:${GIT_COMMIT:-latest}"
                ],
                timeout_seconds=180
            ),
            PipelineStage(
                name="canary_deploy",
                action=f"Deploy candidate build to {target_env} with autonomous canary routing",
                commands=[
                    f"openharness deploy --target '{target_env}' --strategy canary --traffic 10%"
                ],
                timeout_seconds=450
            ),
            PipelineStage(
                name="monitor_and_self_heal",
                action="Continuously monitor health metrics and automatically trigger rollbacks on error budget breach",
                commands=[
                    "openharness monitor --duration 5m --auto-rollback"
                ],
                timeout_seconds=300
            )
        ]

        arch_doc = ArchitectureDoc(
            title="Foundational Architecture Documentation: Autonomous CD Pipeline",
            target_environment=target_env,
            summary=(
                f"Declarative self-healing deployment pipeline generated for prompt: '{prompt}'. "
                f"Configured for target runtime '{target_env}' with automated verification guardrails."
            ),
            self_healing_policy=(
                "Autonomous anomaly detection will monitor system telemetry post-deployment. "
                "If error rate exceeds threshold or health checks fail, the pipeline automatically "
                "reverts traffic to the last known stable release."
            ),
            monitoring_strategy=(
                "Real-time evaluation via OpenHarness telemetry daemon. Tracks latency p99, "
                "HTTP error rates, CPU/memory utilization, and synthetic agent health checks."
            ),
            constraints=constraints
        )

        clean_slug = re.sub(r"[^a-zA-Z0-9]+", "-", prompt.lower()).strip("-")[:30]
        pipeline_name = f"pipeline-{clean_slug}" if clean_slug else "pipeline-ai-generated"

        return PipelinePlan(
            prompt=prompt,
            pipeline_name=pipeline_name,
            target_environment=target_env,
            stages=stages,
            architecture_doc=arch_doc
        )
