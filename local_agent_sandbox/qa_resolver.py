from typing import Optional

from .telemetry.events import EventCategory, record_event


class QAResolver:
    """QA Resolver persona handling QA feedback processing."""

    def resolve_qa(
        self,
        repo: str = "default",
        feedback: str = "",
        positive: bool = True,
        db_path: Optional[str] = None,
    ) -> None:
        """Record qa_feedback telemetry event."""
        record_event(
            category=EventCategory.QA_FEEDBACK,
            persona="qa_resolver",
            repo=repo,
            detail=feedback,
            state="positive" if positive else "negative",
            db_path=db_path,
        )
