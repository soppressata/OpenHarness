from enum import Enum
from typing import Any, Optional, Union

from .config import is_telemetry_enabled
from .merit_ledger import MeritLedger


class EventCategory(str, Enum):
    ISSUE_FILED = "issue_filed"
    PR_MERGED = "pr_merged"
    QA_FEEDBACK = "qa_feedback"
    QUOTA_ROTATION = "quota_rotation"
    HUMAN_CORRECTION = "human_correction"
    BUILD_FAILURE = "build_failure"
    HUMAN_INTERVENTION = "human_intervention"
    ATTESTATION = "attestation"


def record_event(
    category: Union[EventCategory, str],
    persona: str = "system",
    repo: str = "default",
    detail: Any = None,
    state: Any = None,
    db_path: Optional[str] = None,
) -> Optional[int]:
    """Helper to record loop event into local SQLite merit ledger.

    Gated by telemetry feature flag. Returns event ID if recorded, None if disabled.
    """
    if not is_telemetry_enabled():
        return None

    cat_str = category.value if isinstance(category, EventCategory) else str(category)
    ledger = MeritLedger(db_path=db_path)
    return ledger.record_event(
        category=cat_str, persona=persona, repo=repo, detail=detail, state=state
    )


from telemetry.events import *
