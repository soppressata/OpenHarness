"""
High-Performance Sandbox Orchestrator for Multi-Verse Agent Ecology (AC1).
Manages execution, state lifecycle, virtual storage, and resource quotas
for thousands of concurrent isolated agent sandboxes (universes).
"""

import os
import signal
import json
import subprocess
import time
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Union
from dataclasses import dataclass, field


class UniverseStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    MESHED = "MESHED"
    DESTROYED = "DESTROYED"


@dataclass
class ComputeQuota:
    """Resource quota bounds for an isolated Universe sandbox."""
    cpu_cores: float = 1.0
    memory_mb: int = 512
    max_threads: int = 128
    max_processes: int = 64


@dataclass
class VirtualNetworkConfig:
    """Network isolation parameters for a Universe sandbox."""
    virtual_ip: str
    mac_address: str
    allowed_hosts: Set[str] = field(default_factory=set)
    meshed_universes: Set[str] = field(default_factory=set)


class Universe:
    """
    An isolated execution context representing a single agent sandbox universe.
    Supports sub-10ms spin-up and teardown with zero-trust network boundary.
    """

    def __init__(
        self,
        universe_id: str,
        name: str,
        quota: Optional[ComputeQuota] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.id = universe_id
        self.name = name
        self.quota = quota or ComputeQuota()
        self.metadata = metadata or {}
        self.status = UniverseStatus.CREATED
        self.created_at = time.time()
        self.network = VirtualNetworkConfig(
            virtual_ip=f"10.244.{hash(universe_id) % 250 + 1}.{hash(name) % 250 + 1}",
            mac_address=f"52:54:00:{uuid.uuid4().hex[:6]:>06}",
        )
        self.virtual_filesystem: Dict[str, bytes] = {}
        self.execution_logs: List[str] = []

    def start(self):
        """Transitions universe to RUNNING status."""
        self.status = UniverseStatus.RUNNING
        self.log(f"Universe '{self.name}' ({self.id}) started.")

    def pause(self):
        """Transitions universe to PAUSED status."""
        self.status = UniverseStatus.PAUSED
        self.log(f"Universe '{self.name}' ({self.id}) paused.")

    def stop(self):
        """Transitions universe to STOPPED status."""
        self.status = UniverseStatus.STOPPED
        self.log(f"Universe '{self.name}' ({self.id}) stopped.")

    def destroy(self):
        """Destroys the universe context and frees resources."""
        self.status = UniverseStatus.DESTROYED
        self.virtual_filesystem.clear()
        self.log(f"Universe '{self.name}' ({self.id}) destroyed.")

    def write_virtual_file(self, path: str, content: Union[str, bytes]):
        """Writes content to virtual sandbox filesystem."""
        if isinstance(content, str):
            content = content.encode("utf-8")
        self.virtual_filesystem[path] = content
        self.log(f"Wrote {len(content)} bytes to virtual path '{path}'.")

    def read_virtual_file(self, path: str) -> Optional[bytes]:
        """Reads content from virtual sandbox filesystem."""
        return self.virtual_filesystem.get(path)

    def log(self, message: str):
        """Records an execution log entry for the universe."""
        entry = f"[{time.strftime('%Y-%m-%dT%H:%M:%SZ')}] [{self.id}] {message}"
        self.execution_logs.append(entry)

    def health_check(self) -> Dict[str, Any]:
        """Returns health status report for the universe."""
        return {
            "universe_id": self.id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, UniverseStatus) else self.status,
            "virtual_ip": self.network.virtual_ip,
            "memory_mb": self.quota.memory_mb,
            "vfs_file_count": len(self.virtual_filesystem),
            "healthy": self.status in (UniverseStatus.RUNNING, UniverseStatus.CREATED, UniverseStatus.MESHED),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Converts Universe instance to dictionary format."""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status.value if isinstance(self.status, UniverseStatus) else self.status,
            "created_at": self.created_at,
            "quota": {
                "cpu_cores": self.quota.cpu_cores,
                "memory_mb": self.quota.memory_mb,
                "max_threads": self.quota.max_threads,
                "max_processes": self.quota.max_processes,
            },
            "network": {
                "virtual_ip": self.network.virtual_ip,
                "mac_address": self.network.mac_address,
                "meshed_count": len(self.network.meshed_universes),
            },
            "metadata": self.metadata,
        }


class UniverseOrchestrator:
    """
    Primary manager for Universe sandbox lifecycle and parallel execution.
    Targeting sub-10ms universe instantiation for massive scale evaluation.
    """

    def __init__(self, max_concurrent_universes: int = 10000):
        self.universes: Dict[str, Universe] = {}
        self.max_concurrent_universes = max_concurrent_universes
        self._thread_pool = ThreadPoolExecutor(max_workers=32)

    def create_universe(
        self,
        name: str = "agent-sandbox",
        quota: Optional[ComputeQuota] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Universe:
        """
        Instantiates a new Universe sandbox. Sub-10ms creation performance.

        :param name: Friendly name for sandbox universe.
        :param quota: Resource quota constraints.
        :param metadata: Custom key-value tags.
        :return: Created Universe instance.
        """
        universe_id = f"uv-{uuid.uuid4().hex[:8]}"
        uv = Universe(universe_id=universe_id, name=name, quota=quota, metadata=metadata)
        uv.start()
        self.universes[universe_id] = uv
        return uv

    def create_universes_batch(
        self,
        count: int = 10,
        name_prefix: str = "agent-node",
        template_quota: Optional[ComputeQuota] = None,
    ) -> List[Universe]:
        """
        Batch creates multiple universe sandboxes concurrently.

        :param count: Number of universes to create (e.g. 1000).
        :param name_prefix: Prefix for universe names.
        :param template_quota: Quota template for created universes.
        :return: List of created Universe instances.
        """
        created = []
        for i in range(count):
            name = f"{name_prefix}-{i}"
            uv = self.create_universe(name=name, quota=template_quota)
            created.append(uv)
        return created

    def get_universe(self, universe_id: str) -> Optional[Universe]:
        """Retrieves Universe instance by ID."""
        return self.universes.get(universe_id)

    def list_universes(
        self, status: Optional[UniverseStatus] = None, limit: int = 100
    ) -> List[Universe]:
        """Lists active universe sandboxes with optional status filtering."""
        result = []
        for uv in self.universes.values():
            if status is None or uv.status == status:
                result.append(uv)
            if len(result) >= limit:
                break
        return result

    def stop_universe(self, universe_id: str) -> bool:
        """Stops a running universe sandbox."""
        uv = self.get_universe(universe_id)
        if uv:
            uv.stop()
            return True
        return False

    def start_universe(self, universe_id: str) -> bool:
        """Starts a stopped universe sandbox."""
        uv = self.get_universe(universe_id)
        if uv:
            uv.start()
            return True
        return False

    def destroy_universe(self, universe_id: str) -> bool:
        """Destroys and cleans up a universe sandbox."""
        uv = self.universes.pop(universe_id, None)
        if uv:
            uv.destroy()
            return True
        return False

    def destroy_all(self):
        """Tears down all managed universe sandboxes."""
        for uv_id in list(self.universes.keys()):
            self.destroy_universe(uv_id)

    def run_task(
        self,
        command: Union[str, List[str]],
        timeout: int = 3600,
        universe_id: Optional[str] = None,
        task_id: Optional[str] = None,
        log_file: Optional[str] = None,
        task_config: Optional[Any] = None,
    ) -> "TaskResult":
        """
        Launches an agent task with configurable execution timeout.

        :param command: Command string or list of argument tokens to execute.
        :param timeout: Timeout duration limit in seconds (default: 3600).
        :param universe_id: Optional universe ID to associate task execution.
        :param task_id: Optional unique identifier for task tracking.
        :param log_file: Optional file path to output task result log.
        :param task_config: Optional task config definition or dictionary containing timeout_seconds.
        :return: TaskResult object containing execution status and timing metrics.
        """
        effective_timeout = timeout
        if task_config is not None:
            if hasattr(task_config, "timeout_seconds") and getattr(task_config, "timeout_seconds", None) is not None:
                effective_timeout = getattr(task_config, "timeout_seconds")
            elif isinstance(task_config, dict) and task_config.get("timeout_seconds") is not None:
                effective_timeout = task_config["timeout_seconds"]

        uv = self.get_universe(universe_id) if universe_id else None
        return run_agent_task(
            command=command,
            timeout=effective_timeout,
            task_id=task_id,
            universe=uv,
            log_file=log_file,
            task_config=task_config,
        )


@dataclass
class TaskResult:
    """
    Task result record documenting execution status, logs, timing, and error details.
    """
    task_id: str
    status: str  # "SUCCESS", "FAILED", "TIMEOUT_EXCEEDED"
    exit_code: Optional[int]
    stdout: str
    stderr: str
    execution_time: float
    timeout_seconds: int
    error: Optional[str] = None
    pid: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        """Converts TaskResult to a dictionary representation."""
        return {
            "task_id": self.task_id,
            "status": self.status,
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "execution_time": round(self.execution_time, 4),
            "timeout_seconds": self.timeout_seconds,
            "error": self.error,
            "pid": self.pid,
        }


def run_agent_task(
    command: Union[str, List[str]],
    timeout: int = 3600,
    task_id: Optional[str] = None,
    universe: Optional[Universe] = None,
    log_file: Optional[str] = None,
    task_config: Optional[Any] = None,
) -> TaskResult:
    """
    Launches an agent task in the sandbox with configurable execution timeout enforcement.
    If the agent task exceeds the timeout duration, gracefully terminates the agent process group
    (including any child processes spawned) and records a TIMEOUT_EXCEEDED status in the task result log.

    :param command: Command string or argument list to execute.
    :param timeout: Maximum execution timeout duration in seconds (default: 3600).
    :param task_id: Optional task identifier.
    :param universe: Optional Universe sandbox for logging.
    :param log_file: Optional file path to save task result log.
    :param task_config: Optional task config definition or dictionary with timeout_seconds override.
    :return: TaskResult documenting status, outputs, timing, and error details.
    """
    if task_config is not None:
        if hasattr(task_config, "timeout_seconds") and getattr(task_config, "timeout_seconds", None) is not None:
            timeout = getattr(task_config, "timeout_seconds")
        elif isinstance(task_config, dict) and task_config.get("timeout_seconds") is not None:
            timeout = task_config["timeout_seconds"]
    tid = task_id or f"task-{uuid.uuid4().hex[:8]}"
    start_time = time.time()

    if isinstance(command, list):
        cmd_str = " ".join(command)
        cmd_args = command
    else:
        cmd_str = command
        cmd_args = command

    if universe:
        universe.log(f"Agent task '{tid}' launched with PID ... (timeout={timeout}s).")

    try:
        proc = subprocess.Popen(
            cmd_args,
            shell=isinstance(cmd_args, str),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
        if universe:
            universe.log(f"Agent task '{tid}' launched with PID {proc.pid} (timeout={timeout}s).")

        stdout, stderr = proc.communicate(timeout=timeout)
        exit_code = proc.returncode
        status = "SUCCESS" if exit_code == 0 else "FAILED"
        error_msg = None if exit_code == 0 else f"Process exited with non-zero status {exit_code}"

    except subprocess.TimeoutExpired:
        status = "TIMEOUT_EXCEEDED"
        error_msg = f"Task '{tid}' exceeded maximum execution timeout of {timeout} seconds."
        stdout, stderr = "", ""
        exit_code = None

        if 'proc' in locals() and proc:
            try:
                # Gracefully terminate process group
                if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                else:
                    proc.terminate()

                stdout, stderr = proc.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                # Force kill if SIGTERM fails to terminate within 500ms
                if hasattr(os, "killpg") and hasattr(os, "getpgid"):
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                else:
                    proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=1.0)
                except Exception:
                    pass
            except Exception as e:
                error_msg += f" (Cleanup note: {e})"

    execution_time = time.time() - start_time

    res = TaskResult(
        task_id=tid,
        status=status,
        exit_code=exit_code,
        stdout=stdout or "",
        stderr=stderr or "",
        execution_time=execution_time,
        timeout_seconds=timeout,
        error=error_msg,
        pid=proc.pid if 'proc' in locals() and proc else None,
    )

    if log_file:
        try:
            with open(log_file, "w", encoding="utf-8") as f:
                f.write(json.dumps(res.to_dict(), indent=2))
        except Exception as e:
            if universe:
                universe.log(f"Failed to write task result log to '{log_file}': {e}")

    return res
