from typing import Optional

from .telemetry.events import EventCategory, record_event


def handle_quota_error(
    backend_name: str, repo: str = "default", db_path: Optional[str] = None
) -> None:
    """Handle quota error by rotating backend and logging quota_rotation telemetry event."""
    record_event(
        category=EventCategory.QUOTA_ROTATION,
        persona="backend_registry",
        repo=repo,
        detail=f"quota_error:{backend_name}",
        state="rotated",
        db_path=db_path,
    )
