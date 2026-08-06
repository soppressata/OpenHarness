"""
Fleet Worker Node Engine ("The Immune System Worker").
Handles node onboarding, local capability detection, heartbeat emission, and test execution.
"""

import os
import platform
import subprocess
import time
import uuid
import shutil
import sys
from typing import Dict, Optional, Any

from .config import NodeCapability
from .conductor import FleetConductor, WorkerNode


def detect_node_capabilities() -> NodeCapability:
    """Detects local operating system, architecture, GPU presence, and installed browsers."""
    os_name = platform.system().lower()
    arch = platform.machine().lower()

    gpus = 0
    if shutil.which("nvidia-smi"):
        gpus = 1

    browsers = []
    if shutil.which("google-chrome") or shutil.which("chrome"):
        browsers.append("chrome")
    if shutil.which("firefox"):
        browsers.append("firefox")
    if shutil.which("chromium") or shutil.which("chromium-browser"):
        browsers.append("chromium")

    if not browsers:
        browsers = ["headless-default"]

    return NodeCapability(
        os=os_name,
        arch=arch,
        gpus=gpus,
        browsers=browsers,
        custom={"python_version": platform.python_version()}
    )


class FleetWorker:
    """
    Worker daemon instance running on host, container, or VM.
    Emits heartbeats and executes test specs.
    """

    def __init__(
        self,
        conductor: FleetConductor,
        node_id: Optional[str] = None,
        address: str = "127.0.0.1:9444",
        hostname: Optional[str] = None,
    ):
        self.conductor = conductor
        self.node_id = node_id or f"worker-{uuid.uuid4().hex[:8]}"
        self.address = address
        self.hostname = hostname or platform.node()
        self.capabilities = detect_node_capabilities()
        self.registered = False

    def join(self, token: Optional[str] = None) -> WorkerNode:
        """Joins the fleet cluster conductor with zero configuration using signed token."""
        node = self.conductor.register_node(
            address=self.address,
            hostname=self.hostname,
            node_id=self.node_id,
            capabilities=self.capabilities,
            token=token,
        )
        self.registered = True
        return node

    def send_heartbeat(self, cpu_percent: float = 5.0, ram_percent: float = 15.0, active_tasks: int = 0) -> bool:
        """Emits periodic heartbeat to Conductor."""
        if not self.registered:
            self.join()
        return self.conductor.record_heartbeat(
            node_id=self.node_id,
            cpu_percent=cpu_percent,
            ram_percent=ram_percent,
            active_tasks=active_tasks,
        )

    def execute_test(
        self, test_spec_dict: Dict[str, Any], timeout_seconds: int = 60
    ) -> Dict[str, Any]:
        """
        Executes a test spec locally via an isolated pytest subprocess.

        Returns a dict with status ``PASSED``, ``FAILED``, or ``INFRA_ERROR``,
        captured output, and a duration. Missing files or subprocess errors are
        reported as infrastructure errors so the fleet can retry them elsewhere.

        Args:
            test_spec_dict: Test metadata including ``file_path`` and optional
                ``trace_id``.
            timeout_seconds: Maximum execution time for the pytest subprocess.

        Raises:
            ValueError: If ``timeout_seconds`` is not positive.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        test_id = test_spec_dict.get("test_id", "unknown-test")
        file_path = test_spec_dict.get("file_path", "test.py")
        trace_id = test_spec_dict.get("trace_id", "")

        start = time.time()

        if not os.path.exists(file_path):
            duration = time.time() - start
            return {
                "test_id": test_id,
                "node_id": self.node_id,
                "status": "INFRA_ERROR",
                "error_message": f"Test file not found: {file_path}",
                "stack_trace": "",
                "duration_seconds": duration,
                "file_path": file_path,
                "trace_id": trace_id,
            }

        try:
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", file_path, "-v", "--tb=short"],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
            duration = time.time() - start
            output = f"{proc.stdout}\n{proc.stderr}".strip()
            if proc.returncode == 0:
                status = "PASSED"
                error_message = ""
                stack_trace = ""
            else:
                status = "FAILED"
                error_message = output.splitlines()[-1] if output else "pytest failed"
                stack_trace = output
        except subprocess.TimeoutExpired:
            duration = time.time() - start
            status = "INFRA_ERROR"
            error_message = f"Test timed out after {timeout_seconds}s: {file_path}"
            stack_trace = ""
        except Exception as exc:  # pragma: no cover - defensive fallback
            duration = time.time() - start
            status = "INFRA_ERROR"
            error_message = f"Failed to execute test: {exc}"
            stack_trace = ""

        return {
            "test_id": test_id,
            "node_id": self.node_id,
            "status": status,
            "error_message": error_message,
            "stack_trace": stack_trace,
            "duration_seconds": duration,
            "file_path": file_path,
            "trace_id": trace_id,
        }
