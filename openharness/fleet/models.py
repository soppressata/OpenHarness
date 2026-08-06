"""
Fleet models for OpenHarness HarnessFleet.
Defines the core data structures for worker nodes, capabilities, and fleet configuration.
"""
from __future__ import annotations

import enum
import time
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class NodeState(str, enum.Enum):
    """Health state of a fleet worker node."""

    HEALTHY = "HEALTHY"
    UNHEALTHY = "UNHEALTHY"
    QUARANTINED = "QUARANTINED"


class WorkerCapabilities(BaseModel):
    """Hardware/software capabilities advertised by a worker node."""

    os: str = "linux"
    arch: str = "x86_64"
    gpu: bool = False
    browsers: List[str] = Field(default_factory=list)
    labels: Dict[str, str] = Field(default_factory=dict)

    def matches(self, requirements: Dict[str, Any]) -> bool:
        """Return True if these capabilities satisfy all given requirements."""
        for key, value in requirements.items():
            if key == "os":
                if self.os != value:
                    return False
            elif key == "arch":
                if self.arch != value:
                    return False
            elif key == "gpu":
                if value and not self.gpu:
                    return False
            elif key.startswith("label:"):
                label_key = key[6:]
                if self.labels.get(label_key) != value:
                    return False
            elif key == "browser":
                if value not in self.browsers:
                    return False
            else:
                if self.labels.get(key) != value:
                    return False
        return True


class WorkerSpec(BaseModel):
    """Static specification for a worker pool entry in fleet.yaml."""

    id: Optional[str] = None
    host: str = "127.0.0.1"
    port: int = 9000
    capabilities: WorkerCapabilities = Field(default_factory=WorkerCapabilities)
    ephemeral: bool = False
    labels: Dict[str, str] = Field(default_factory=dict)


class FleetConfig(BaseModel):
    """Top-level configuration for a HarnessFleet deployment."""

    version: str = "1.0"
    conductor: Dict[str, Any] = Field(default_factory=lambda: {
        "host": "0.0.0.0",
        "port": 8900,
        "heartbeat_interval_sec": 5,
        "heartbeat_miss_threshold": 3,
    })
    workers: List[WorkerSpec] = Field(default_factory=list)
    scheduling: Dict[str, Any] = Field(default_factory=lambda: {
        "shard_mode": "auto",
        "max_skew_pct": 20,
        "default_timeout_sec": 300,
    })


class WorkerNode(BaseModel):
    """Runtime state of a registered worker node."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:12])
    host: str = "127.0.0.1"
    port: int = 9000
    capabilities: WorkerCapabilities = Field(default_factory=WorkerCapabilities)
    ephemeral: bool = False
    state: NodeState = NodeState.HEALTHY
    last_heartbeat: float = Field(default_factory=time.time)
    consecutive_missed: int = 0
    infra_errors: int = 0
    infra_error_window_start: float = Field(default_factory=time.time)
    registered_at: float = Field(default_factory=time.time)
    labels: Dict[str, str] = Field(default_factory=dict)

    def is_responsive(self, now: float, miss_threshold: int) -> bool:
        """Check if the node has not exceeded the missed heartbeat threshold."""
        return self.consecutive_missed < miss_threshold


class TestAssignment(BaseModel):
    """A single test file assigned to a specific worker node."""

    test_file: str
    worker_id: str
    shard_index: int = 0
    shard_total: int = 1
