import os
from datetime import datetime, timezone
from typing import Optional

from .. import gh_utils
from .config import is_telemetry_enabled
from .merit_ledger import MeritLedger


def generate_feedback_digest(db_path: Optional[str] = None) -> str:
    """Aggregate merit ledger events into markdown digest content."""
    if not is_telemetry_enabled():
        return ""

    ledger = MeritLedger(db_path=db_path)
    events = ledger.get_events()

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Global Reward Telemetry & Merit Ledger Digest",
        f"**Generated at:** {now_str}",
        f"**Total Events:** {len(events)}",
        "",
        "## Event Breakdown by Category",
        "| ID | Timestamp | Category | Persona | Repo | State | Detail |",
        "|---|---|---|---|---|---|---|",
    ]

    for ev in events:
        detail_short = str(ev.get("detail", "")).replace("\n", " ")[:60]
        lines.append(
            f"| {ev['id']} | {ev['timestamp']} | {ev['category']} | {ev['persona']} | {ev['repo']} | {ev['state']} | {detail_short} |"
        )

    lines.append("")
    lines.append("---")
    lines.append("*OpenHarness Autonomic Evolution Engine Telemetry*")

    return "\n".join(lines)


def push_feedback_digest(
    db_path: Optional[str] = None,
    feedback_path: str = "FEEDBACK.md",
    repo: str = "default",
) -> bool:
    """Write FEEDBACK.md and push to GitHub via gh CLI."""
    if not is_telemetry_enabled():
        return False

    content = generate_feedback_digest(db_path=db_path)
    with open(feedback_path, "w", encoding="utf-8") as f:
        f.write(content)

    try:
        gh_utils.gh(
            f"gist create {feedback_path} --desc 'Daily Merit Ledger Telemetry Digest'"
        )
        return True
    except Exception:
        return False


from telemetry.feedback_digest import *
