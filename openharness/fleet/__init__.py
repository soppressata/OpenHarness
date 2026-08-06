"""
HarnessFleet - Distributed, Self-Healing AI Test Grid with Intelligent Orchestration.
Package initialization and public API exports.
"""

from .config import (
    FleetConfig,
    NodeCapability,
    load_config,
    save_config,
    generate_default_config,
    migrate_config,
)
from .conductor import (
    FleetConductor,
    WorkerNode,
    NodeStatus,
)
from .scheduler import (
    FleetScheduler,
    TestSpec,
    TestShard,
)
from .worker import (
    FleetWorker,
    detect_node_capabilities,
)
from .self_healing import (
    FleetSelfHealingEngine,
    TestExecutionResult,
    ErrorType,
)
from .retry import (
    FailureType,
    classify_failure,
    should_retry,
    backoff_delay,
    calculate_retry_delay,
)
from .observability import (
    FleetObservabilityDashboard,
    FailureFingerprinter,
    FailureCluster,
    generate_trace_id,
)
from .cli_fleet import (
    handle_fleet_init,
    handle_fleet_join,
    handle_fleet_run,
    handle_fleet_status,
    handle_fleet_dashboard,
    handle_fleet_migrate,
)

__all__ = [
    "FleetConfig",
    "NodeCapability",
    "load_config",
    "save_config",
    "generate_default_config",
    "migrate_config",
    "FleetConductor",
    "WorkerNode",
    "NodeStatus",
    "FleetScheduler",
    "TestSpec",
    "TestShard",
    "FleetWorker",
    "detect_node_capabilities",
    "FleetSelfHealingEngine",
    "TestExecutionResult",
    "ErrorType",
    "FailureType",
    "classify_failure",
    "should_retry",
    "backoff_delay",
    "calculate_retry_delay",
    "FleetObservabilityDashboard",
    "FailureFingerprinter",
    "FailureCluster",
    "generate_trace_id",
    "handle_fleet_init",
    "handle_fleet_join",
    "handle_fleet_run",
    "handle_fleet_status",
    "handle_fleet_dashboard",
    "handle_fleet_migrate",
]
