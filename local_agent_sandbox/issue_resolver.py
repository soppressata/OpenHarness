from typing import Optional

from .telemetry.events import EventCategory, record_event


class IssueResolver:
    """Issue Resolver persona filing and processing repo issues."""

    def resolve_issue(
        self, issue_id: str, repo: str = "default", db_path: Optional[str] = None
    ) -> None:
        """Record issue_filed telemetry event."""
        record_event(
            category=EventCategory.ISSUE_FILED,
            persona="issue_resolver",
            repo=repo,
            detail=f"issue:{issue_id}",
            state="resolved",
            db_path=db_path,
        )
