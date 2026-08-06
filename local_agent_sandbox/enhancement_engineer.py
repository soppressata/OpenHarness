from typing import Optional

from .telemetry.events import EventCategory, record_event


class EnhancementEngineer:
    """Enhancement Engineer persona handling PR merges and build checks."""

    def on_merge_success(
        self,
        repo: str = "default",
        detail: str = "PR merged cleanly",
        db_path: Optional[str] = None,
    ) -> None:
        """Record pr_merged telemetry event on merge success."""
        record_event(
            category=EventCategory.PR_MERGED,
            persona="enhancement_engineer",
            repo=repo,
            detail=detail,
            state="success",
            db_path=db_path,
        )

    def on_merge_failure(
        self,
        repo: str = "default",
        detail: str = "Build or merge failed",
        db_path: Optional[str] = None,
    ) -> None:
        """Record build_failure telemetry event on merge/build failure."""
        record_event(
            category=EventCategory.BUILD_FAILURE,
            persona="enhancement_engineer",
            repo=repo,
            detail=detail,
            state="failure",
            db_path=db_path,
        )
