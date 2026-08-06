from typing import Optional

from .telemetry.events import EventCategory, record_event


class Daemon:
    """Daemon running loop iterations and emitting telemetry events."""

    def run_cycle(self, repo: str = "default", db_path: Optional[str] = None) -> None:
        """Execute a daemon cycle iteration emitting telemetry event."""
        record_event(
            category=EventCategory.HUMAN_INTERVENTION,
            persona="daemon",
            repo=repo,
            detail="cycle_started",
            state="running",
            db_path=db_path,
        )
