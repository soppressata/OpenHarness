import json
import os
import sqlite3
import pytest

from local_agent_sandbox.backend_registry import handle_quota_error
from local_agent_sandbox.daemon import Daemon
from local_agent_sandbox.enhancement_engineer import EnhancementEngineer
from local_agent_sandbox.issue_resolver import IssueResolver
from local_agent_sandbox.qa_resolver import QAResolver
from local_agent_sandbox.qa_tester import QATester
from local_agent_sandbox.telemetry import (
    EventCategory,
    MeritLedger,
    generate_feedback_digest,
    get_persona_override,
    get_persona_prompt_suffix,
    harvest_corrections,
    is_telemetry_enabled,
    parse_harvest_directive,
    push_feedback_digest,
    record_event,
    score_personas,
    set_telemetry_enabled,
    update_reward_model,
)


@pytest.fixture(autouse=True)
def reset_telemetry_flag():
    set_telemetry_enabled(True)
    yield
    set_telemetry_enabled(None)


def test_schema_migration(tmp_path):
    db_path = str(tmp_path / "merit.db")
    ledger = MeritLedger(db_path=db_path)

    # Verify schema version is at least 1
    assert ledger.get_schema_version() >= 1

    # Verify tables exist
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [r[0] for r in cursor.fetchall()]
    assert "schema_version" in tables
    assert "events" in tables
    conn.close()


def test_event_recording(tmp_path):
    db_path = str(tmp_path / "merit.db")
    categories = [
        EventCategory.ISSUE_FILED,
        EventCategory.PR_MERGED,
        EventCategory.QA_FEEDBACK,
        EventCategory.QUOTA_ROTATION,
        EventCategory.HUMAN_CORRECTION,
        EventCategory.BUILD_FAILURE,
        EventCategory.HUMAN_INTERVENTION,
        EventCategory.ATTESTATION,
    ]

    for cat in categories:
        event_id = record_event(
            category=cat,
            persona="test_persona",
            repo="test/repo",
            detail={"key": "val"},
            state="success",
            db_path=db_path,
        )
        assert event_id is not None and event_id > 0

    ledger = MeritLedger(db_path=db_path)
    events = ledger.get_events()
    assert len(events) == len(categories)
    recorded_cats = {ev["category"] for ev in events}
    expected_cats = {cat.value for cat in categories}
    assert recorded_cats == expected_cats


def test_harvest_parsing(tmp_path, monkeypatch):
    comment_text = """
    Nice work on this PR!
    HARVEST: {"directive": "enforce_strict_types", "priority": "high"}
    Some irrelevant comment
    HARVEST: simple text correction directive
    """

    directives = parse_harvest_directive(comment_text)
    assert len(directives) == 2
    assert directives[0] == {"directive": "enforce_strict_types", "priority": "high"}
    assert directives[1] == {"raw_directive": "simple text correction directive"}

    # Test harvest_corrections with mocked gh output
    db_path = str(tmp_path / "merit.db")
    mock_pr_response = json.dumps(
        [
            {
                "number": 42,
                "title": "Add feature",
                "comments": [{"body": 'HARVEST: {"fix": "add_type_annotations"}'}],
            }
        ]
    )

    import local_agent_sandbox.gh_utils as gh_utils

    monkeypatch.setattr(gh_utils, "gh", lambda args: mock_pr_response)

    results = harvest_corrections(repo="test/repo", db_path=db_path)
    assert len(results) == 1
    assert results[0]["pr_number"] == 42
    assert results[0]["payload"] == {"fix": "add_type_annotations"}

    ledger = MeritLedger(db_path=db_path)
    events = ledger.get_events(category="human_correction")
    assert len(events) == 1
    assert events[0]["persona"] == "human"


def test_reward_model_scoring_and_prompt_mutation(tmp_path):
    db_path = str(tmp_path / "merit.db")
    overrides_path = str(tmp_path / "overrides.json")

    # Record merge success and QA feedback events
    record_event(
        category=EventCategory.PR_MERGED,
        persona="qa_tester",
        repo="repo",
        db_path=db_path,
    )
    record_event(
        category=EventCategory.QA_FEEDBACK,
        persona="qa_tester",
        repo="repo",
        state="positive",
        db_path=db_path,
    )

    overrides = update_reward_model(db_path=db_path, overrides_path=overrides_path)
    assert os.path.exists(overrides_path)
    assert "qa_tester" in overrides
    assert "prompt_suffix" in overrides["qa_tester"]

    # Verify prompt suffix is injected into QATester prompt within 10 cycles
    qa_tester = QATester()
    base_prompt = "You are a QA Tester agent."
    mutated_prompt = base_prompt

    for cycle in range(1, 11):
        mutated_prompt = qa_tester.run_qa_test(
            base_prompt, repo="repo", db_path=db_path, overrides_path=overrides_path
        )
        if mutated_prompt != base_prompt:
            break

    assert mutated_prompt != base_prompt
    assert "[Reward Telemetry]" in mutated_prompt


def test_feedback_digest(tmp_path, monkeypatch):
    db_path = str(tmp_path / "merit.db")
    record_event(
        category=EventCategory.ISSUE_FILED,
        persona="issue_resolver",
        repo="test/repo",
        detail="Bug found",
        state="resolved",
        db_path=db_path,
    )

    digest = generate_feedback_digest(db_path=db_path)
    assert "# Global Reward Telemetry & Merit Ledger Digest" in digest
    assert "issue_filed" in digest
    assert "issue_resolver" in digest

    import local_agent_sandbox.gh_utils as gh_utils

    monkeypatch.setattr(gh_utils, "gh", lambda args: "https://gist.github.com/123")

    feedback_path = str(tmp_path / "FEEDBACK.md")
    success = push_feedback_digest(db_path=db_path, feedback_path=feedback_path)
    assert success is True
    assert os.path.exists(feedback_path)


def test_telemetry_disabled_flag(tmp_path, monkeypatch):
    db_path = str(tmp_path / "merit.db")
    set_telemetry_enabled(False)

    assert is_telemetry_enabled() is False

    # All calls must be no-ops
    event_id = record_event(
        category=EventCategory.PR_MERGED,
        persona="qa_tester",
        repo="repo",
        db_path=db_path,
    )
    assert event_id is None

    harvested = harvest_corrections(repo="repo", db_path=db_path)
    assert harvested == []

    overrides = update_reward_model(
        db_path=db_path, overrides_path=str(tmp_path / "overrides.json")
    )
    assert overrides == {}

    digest = generate_feedback_digest(db_path=db_path)
    assert digest == ""


def test_feature_flag_env_and_file_parsing(tmp_path, monkeypatch):
    set_telemetry_enabled(None)  # clear explicit override

    # Test env var AUTOLOOP_FEATURES=0
    monkeypatch.setenv("AUTOLOOP_FEATURES", "0")
    assert is_telemetry_enabled() is False

    # Test env var AUTOLOOP_FEATURES=1
    monkeypatch.setenv("AUTOLOOP_FEATURES", "1")
    assert is_telemetry_enabled() is True

    monkeypatch.delenv("AUTOLOOP_FEATURES", raising=False)

    # Test features.json
    orig_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        with open("features.json", "w") as f:
            json.dump({"telemetry": {"enabled": False}}, f)
        assert is_telemetry_enabled() is False

        with open("features.json", "w") as f:
            json.dump({"telemetry.enabled": True}, f)
        assert is_telemetry_enabled() is True
    finally:
        os.chdir(orig_cwd)


def test_worker_module_hooks(tmp_path):
    db_path = str(tmp_path / "merit.db")

    Daemon().run_cycle(repo="test/repo", db_path=db_path)
    EnhancementEngineer().on_merge_success(
        repo="test/repo", detail="Success", db_path=db_path
    )
    EnhancementEngineer().on_merge_failure(
        repo="test/repo", detail="Failed", db_path=db_path
    )
    QAResolver().resolve_qa(
        repo="test/repo", feedback="Good", positive=True, db_path=db_path
    )
    handle_quota_error("ollama", repo="test/repo", db_path=db_path)
    IssueResolver().resolve_issue("101", repo="test/repo", db_path=db_path)

    ledger = MeritLedger(db_path=db_path)
    events = ledger.get_events()
    assert len(events) == 6
    personas = {ev["persona"] for ev in events}
    assert personas == {
        "daemon",
        "enhancement_engineer",
        "qa_resolver",
        "backend_registry",
        "issue_resolver",
    }
