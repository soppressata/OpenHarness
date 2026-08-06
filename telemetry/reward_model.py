import json
import os
from typing import Dict, Optional

from .config import is_telemetry_enabled
from .merit_ledger import MeritLedger

DEFAULT_OVERRIDES_PATH = os.path.join("telemetry", "overrides.json")


def score_personas(db_path: Optional[str] = None) -> Dict[str, dict]:
    """Score personas based on merit ledger event history."""
    ledger = MeritLedger(db_path=db_path)
    events = ledger.get_events()

    persona_stats: Dict[str, dict] = {}
    for ev in events:
        persona = ev["persona"]
        if persona not in persona_stats:
            persona_stats[persona] = {
                "pr_merged": 0,
                "build_failure": 0,
                "qa_positive": 0,
                "qa_negative": 0,
                "human_correction": 0,
                "total_events": 0,
            }
        stats = persona_stats[persona]
        stats["total_events"] += 1
        cat = ev["category"]
        if cat == "pr_merged":
            stats["pr_merged"] += 1
        elif cat == "build_failure":
            stats["build_failure"] += 1
        elif cat == "qa_feedback":
            state = (ev.get("state") or "").lower()
            if "positive" in state or state == "success":
                stats["qa_positive"] += 1
            else:
                stats["qa_negative"] += 1
        elif cat == "human_correction":
            stats["human_correction"] += 1

    overrides: Dict[str, dict] = {}
    all_personas = set(persona_stats.keys()).union(
        {"qa_tester", "enhancement_engineer"}
    )

    for persona in all_personas:
        stats = persona_stats.get(
            persona,
            {
                "pr_merged": 0,
                "build_failure": 0,
                "qa_positive": 0,
                "qa_negative": 0,
                "human_correction": 0,
                "total_events": 0,
            },
        )
        merges = stats["pr_merged"]
        failures = stats["build_failure"]
        total_merge_attempts = merges + failures
        merge_success_rate = (
            (merges / total_merge_attempts) if total_merge_attempts > 0 else 1.0
        )
        feedback_delta = stats["qa_positive"] - stats["qa_negative"]
        corrections = stats["human_correction"]
        adherence_score = max(0.0, 1.0 - (corrections * 0.1))

        prompt_suffix = (
            f"\n[Reward Telemetry] Persona: {persona} | "
            f"Merge Success: {merge_success_rate:.0%} | "
            f"Feedback Delta: {feedback_delta:+d} | "
            f"Adherence: {adherence_score:.2f}"
        )
        plan_template = (
            "strict_adherence_v2" if corrections > 0 else "standard_flow_v1"
        )
        quota_weight = max(0.5, min(2.0, 1.0 + (feedback_delta * 0.1)))

        overrides[persona] = {
            "prompt_suffix": prompt_suffix,
            "plan_template": plan_template,
            "quota_weight": round(quota_weight, 2),
            "metrics": {
                "merge_success_rate": round(merge_success_rate, 4),
                "feedback_delta": feedback_delta,
                "adherence_score": round(adherence_score, 4),
            },
        }

    return overrides


def update_reward_model(
    db_path: Optional[str] = None, overrides_path: Optional[str] = None
) -> Dict[str, dict]:
    """Score each persona from ledger rows and write drifting-config overrides file."""
    if not is_telemetry_enabled():
        return {}

    out_path = overrides_path or DEFAULT_OVERRIDES_PATH
    out_dir = os.path.dirname(out_path)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    overrides = score_personas(db_path=db_path)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, indent=2)

    return overrides


def get_persona_override(
    persona: str, overrides_path: Optional[str] = None
) -> dict:
    """Retrieve reward model overrides for a given persona."""
    if not is_telemetry_enabled():
        return {}

    path = overrides_path or DEFAULT_OVERRIDES_PATH
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get(persona, {})
        except Exception:
            pass
    return {}


def get_persona_prompt_suffix(
    persona: str, overrides_path: Optional[str] = None
) -> str:
    """Retrieve prompt suffix for a persona from overrides file."""
    override = get_persona_override(persona, overrides_path=overrides_path)
    return override.get("prompt_suffix", "")
