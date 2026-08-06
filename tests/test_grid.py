"""
Test Suite for Harness Grid (openharness.grid).

Covers the Observer / Global Replay ledger (hash-chained, tamper-evident,
exactly-once, byte-for-byte replay), node leave with in-flight re-dispatch,
health-watch convergence, and the ``harness grid`` CLI commands.
"""

import json
import os
import sqlite3
import time

import pytest
from click.testing import CliRunner

from openharness.cli.main import cli
from openharness.fleet import FleetConductor, NodeStatus, handle_fleet_run
from openharness.grid import (
    GridLedger,
    GridResult,
    handle_grid_init,
    handle_grid_join,
    handle_grid_leave,
    handle_grid_replay,
    handle_grid_status,
    handle_grid_watch,
)


def test_grid_ledger_exactly_once_and_chain(tmp_path):
    ledger = GridLedger(str(tmp_path / "ledger.db"))
    res1 = GridResult(test_id="test_a", node_id="node-1", status="PASSED", trace_id="t1", committed_at=100.0)
    assert ledger.append(res1) is True
    duplicate = GridResult(test_id="test_a", node_id="node-1", status="PASSED", trace_id="t1", committed_at=101.0)
    assert ledger.append(duplicate) is False

    res2 = GridResult(test_id="test_b", node_id="node-2", status="FAILED", error_message="boom", trace_id="t2", committed_at=102.0)
    assert ledger.append(res2) is True
    assert ledger.count() == 2
    assert ledger.verify() == []


def test_grid_ledger_replay_byte_for_byte(tmp_path):
    ledger = GridLedger(str(tmp_path / "ledger.db"))
    result = GridResult(
        test_id="test_3",
        node_id="node-1",
        status="FAILED",
        error_message="AssertionError: expected True got False",
        stack_trace="line 12\nassert x == y",
        duration_seconds=1.234,
        trace_id="tr-abc",
        committed_at=1234.5,
    )
    assert ledger.append(result) is True

    payload = ledger.replay_payload("test_3", 1234.5)
    assert payload == result.to_payload_json()

    replayed = ledger.replay("test_3", 1234.5)
    assert replayed is not None
    assert replayed.to_payload_json() == payload
    assert replayed.test_id == "test_3"
    assert replayed.node_id == "node-1"
    assert replayed.status == "FAILED"


def test_grid_ledger_replay_history(tmp_path):
    ledger = GridLedger(str(tmp_path / "ledger.db"))
    ledger.append(GridResult(test_id="test_x", node_id="n1", status="FAILED", trace_id="a", committed_at=100.0))
    ledger.append(GridResult(test_id="test_x", node_id="n1", status="PASSED", trace_id="b", committed_at=200.0))

    assert ledger.replay("test_x", 100.0).trace_id == "a"
    assert ledger.replay("test_x", 150.0).trace_id == "a"
    assert ledger.replay("test_x", 200.0).trace_id == "b"
    assert ledger.replay("test_x", 999.0).trace_id == "b"
    assert ledger.replay("test_x", 50.0) is None
    assert ledger.latest("test_x").trace_id == "b"


def test_grid_ledger_verify_detects_tampering(tmp_path):
    db_path = str(tmp_path / "ledger.db")
    ledger = GridLedger(db_path)
    ledger.append(GridResult(test_id="test_a", node_id="n1", status="PASSED", trace_id="t1", committed_at=1.0))
    ledger.append(GridResult(test_id="test_b", node_id="n2", status="FAILED", trace_id="t2", committed_at=2.0))
    assert ledger.verify() == []

    conn = sqlite3.connect(db_path)
    conn.execute("UPDATE grid_ledger SET payload_json = 'tampered' WHERE test_id = 'test_a'")
    conn.commit()
    conn.close()

    violations = ledger.verify()
    assert len(violations) == 1
    assert "test_a:t1" in violations[0]


def test_grid_leave_redispatch():
    cond = FleetConductor()
    cond.register_node("127.0.0.1:9444", node_id="node-leave", hostname="departing")
    cond.register_node("127.0.0.1:9445", node_id="node-healthy-1", hostname="peer-1")
    cond.register_node("127.0.0.1:9446", node_id="node-healthy-2", hostname="peer-2")

    report = handle_grid_leave(
        "node-leave",
        in_flight=["shard_1", "shard_2", "shard_3"],
        conductor=cond,
    )
    assert report["left_node"] == "node-leave"
    assert report["status"] == "DRAINED"
    assert cond.nodes["node-leave"].status == NodeStatus.DRAINING
    assert set(report["redispatched"].keys()) == {"node-healthy-1", "node-healthy-2"}
    flat = [s for shards in report["redispatched"].values() for s in shards]
    assert sorted(flat) == ["shard_1", "shard_2", "shard_3"]
    assert report["undispatched"] == []


def test_grid_leave_no_healthy_peers():
    cond = FleetConductor()
    cond.register_node("127.0.0.1:9444", node_id="node-only", hostname="solo")

    report = handle_grid_leave("node-only", in_flight=["shard_1", "shard_2"], conductor=cond)
    assert report["redispatched"] == {}
    assert report["undispatched"] == ["shard_1", "shard_2"]

    with pytest.raises(ValueError, match="Unknown grid node"):
        handle_grid_leave("ghost", conductor=cond)


def test_grid_watch_convergence():
    cond = FleetConductor()
    cond.register_node("127.0.0.1:9444", node_id="node-watch", hostname="watched")

    report = handle_grid_watch(iterations=1, interval=0.0, conductor=cond)
    assert report["final"]["unhealthy"] == 0
    assert report["converged"] is True

    cond.nodes["node-watch"].last_heartbeat = time.time() - 30.0
    report = handle_grid_watch(iterations=1, interval=0.0, conductor=cond)
    assert report["final"]["unhealthy"] == 1
    assert report["converged"] is False

    cond.record_heartbeat("node-watch", cpu_percent=5.0, ram_percent=10.0)
    report = handle_grid_watch(iterations=1, interval=0.0, conductor=cond)
    assert report["final"]["unhealthy"] == 0
    assert report["converged"] is True


def test_grid_replay_end_to_end_via_fleet_run(tmp_path):
    test_file = tmp_path / "test_example.py"
    test_file.write_text("def test_example():\n    assert True\n", encoding="utf-8")
    cfg = str(tmp_path / "fleet.yaml")
    handle_grid_init(output_path=cfg)
    ledger_path = str(tmp_path / "ledger.db")

    exit_code = handle_fleet_run(
        test_files=[str(test_file)],
        nodes_count=1,
        shards="auto",
        config_path=cfg,
        ledger_path=ledger_path,
    )
    assert exit_code == 0

    ledger = GridLedger(ledger_path)
    assert ledger.count() == 1
    assert ledger.verify() == []

    committed_at = ledger.latest("test_1").committed_at
    replayed = handle_grid_replay(f"test_1@{committed_at}", ledger_path=ledger_path)
    payload = json.loads(replayed["payload_json"])
    assert payload["test_id"] == "test_1"
    assert payload["status"] == "PASSED"
    assert payload["node_id"].startswith("worker-")


def test_grid_replay_invalid_spec_and_missing(tmp_path):
    ledger_path = str(tmp_path / "ledger.db")
    with pytest.raises(ValueError, match="test_id"):
        handle_grid_replay("justtestid", ledger_path=ledger_path)
    with pytest.raises(ValueError, match="timestamp"):
        handle_grid_replay("test@abc", ledger_path=ledger_path)
    with pytest.raises(LookupError):
        handle_grid_replay("missing@100.0", ledger_path=ledger_path)


def test_cli_grid_init_status_join_watch(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner = CliRunner()

    res = runner.invoke(cli, ["grid", "init"])
    assert res.exit_code == 0
    assert (tmp_path / "fleet.yaml").exists()

    res = runner.invoke(cli, ["grid", "status", "--config", "fleet.yaml"])
    assert res.exit_code == 0
    assert "Grid Status" in res.output

    res = runner.invoke(cli, ["grid", "join"])
    assert res.exit_code == 0
    assert "joined the grid" in res.output

    res = runner.invoke(cli, ["grid", "watch", "--iterations", "1", "--interval", "0.0", "--config", "fleet.yaml"])
    assert res.exit_code == 0
    assert "converged" in res.output


def test_cli_grid_replay(tmp_path):
    ledger_path = str(tmp_path / "ledger.db")
    ledger = GridLedger(ledger_path)
    ledger.append(
        GridResult(
            test_id="test_9",
            node_id="node-1",
            status="FAILED",
            error_message="boom",
            trace_id="t9",
            committed_at=500.0,
        )
    )

    runner = CliRunner()
    res = runner.invoke(cli, ["grid", "replay", "test_9@500.0", "--ledger", ledger_path])
    assert res.exit_code == 0
    assert '"test_id":"test_9"' in res.output
    assert "boom" in res.output
