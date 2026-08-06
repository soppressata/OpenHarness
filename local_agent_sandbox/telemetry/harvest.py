import json
import re
from typing import Any, List, Optional

from .. import gh_utils
from .config import is_telemetry_enabled
from .events import EventCategory, record_event


def parse_harvest_directive(text: str) -> List[dict]:
    """Extract and parse HARVEST: directives from comment text."""
    results = []
    lines = text.splitlines()
    for line in lines:
        match = re.search(r"HARVEST:\s*(.*)", line, re.IGNORECASE)
        if match:
            payload_str = match.group(1).strip()
            try:
                payload = json.loads(payload_str)
            except Exception:
                payload = {"raw_directive": payload_str}
            results.append(payload)
    return results


def harvest_corrections(
    repo: str = "default", db_path: Optional[str] = None
) -> List[dict]:
    """Poll open PR comments for HARVEST directives, record human_correction events, and return payloads."""
    if not is_telemetry_enabled():
        return []

    harvested = []
    try:
        raw_prs = gh_utils.gh("pr list --state open --json number,title,comments")
        if raw_prs:
            try:
                prs = json.loads(raw_prs)
            except Exception:
                prs = []

            for pr in prs:
                comments = pr.get("comments", [])
                for comment in comments:
                    body = (
                        comment.get("body", "")
                        if isinstance(comment, dict)
                        else str(comment)
                    )
                    directives = parse_harvest_directive(body)
                    for payload in directives:
                        event_id = record_event(
                            category=EventCategory.HUMAN_CORRECTION,
                            persona="human",
                            repo=repo,
                            detail=payload,
                            state="harvested",
                            db_path=db_path,
                        )
                        harvested.append(
                            {
                                "event_id": event_id,
                                "pr_number": pr.get("number"),
                                "payload": payload,
                            }
                        )
    except Exception:
        pass

    return harvested
