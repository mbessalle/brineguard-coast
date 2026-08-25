"""Tests for tools/watchdog.py and tools/ledger_stats.py.

All tests use synthetic ledger/state fixtures in tmp dirs and mocked
subprocess — NO live orca calls.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO_ROOT, "tools")
sys.path.insert(0, TOOLS)

import ledger_stats  # noqa: E402
import watchdog  # noqa: E402
from watchdog import run as watchdog_run  # noqa: E402
from ledger_stats import run as ledger_stats_run  # noqa: E402


# ============================================================================
# Helpers
# ============================================================================

def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")


class _FakeSubprocess:
    """Replaces subprocess.run with a callable that returns canned JSON
    from a sequence of dicts. Each entry may be:
      - a dict → returned as stdout for dispatch-show
      - ("_term", dict) → returned as stdout for terminal-read
      - ("_raise", str) → raises OSError
    """

    def __init__(self, calls: list):
        self.calls = calls
        self._idx = 0

    def __call__(self, argv, capture_output=True, text=True, timeout=None, **kw):
        cmd = " ".join(argv)
        if self._idx >= len(self.calls):
            return self._result(json.dumps({"ok": True}))
        entry = self.calls[self._idx]
        self._idx += 1
        if isinstance(entry, tuple) and entry[0] == "_raise":
            raise OSError(entry[1])
        if isinstance(entry, tuple) and entry[0] == "_term":
            return self._result(json.dumps(entry[1]))
        if isinstance(entry, tuple) and entry[0] == "_timeout":
            raise subprocess.TimeoutExpired(cmd, entry[1])
        return self._result(json.dumps(entry))

    def _result(self, stdout_text):
        return _FakeResult(stdout_text)


class _FakeResult:
    def __init__(self, stdout_text):
        self.stdout = stdout_text
        self.stderr = ""
        self.returncode = 0


# ============================================================================
# watchdog — classification
# ============================================================================

def test_classify_completed(tmp_path, monkeypatch):
    """orca status=completed → COMPLETED."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "completed",
                                             "completed_at": "2026-08-26T00:05:00+00:00"}}}
    terminal_read = {"result": {"buffer": "pi> "}}
    fake = _FakeSubprocess([dispatch_show, ("_term", terminal_read)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["rows"] == 1
    assert report["dispatches"][0]["state"] == "COMPLETED"


def test_classify_blocked(tmp_path, monkeypatch):
    """Tail matches question/blocked pattern → BLOCKED."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "dispatched"}}}
    terminal_read = {"result": {"buffer": "… orca orchestration ask …"}}
    fake = _FakeSubprocess([dispatch_show, ("_term", terminal_read)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0  # BLOCKED does not cause exit 1
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["dispatches"][0]["state"] == "BLOCKED"
    assert "escalation_triage" in report["dispatches"][0]["playbook"]


def test_classify_dead_terminal_gone(tmp_path, monkeypatch):
    """Terminal read raises OSError → DEAD."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_gone", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "dispatched"}}}
    fake = _FakeSubprocess([dispatch_show, ("_raise", "terminal gone")])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 1  # DEAD → exit 1
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["dispatches"][0]["state"] == "DEAD"
    assert "dispatch_recovery.md §3" in report["dispatches"][0]["playbook"]


def test_classify_quiet(tmp_path, monkeypatch):
    """Tail sha unchanged for > quiet_s → QUIET."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    tail_text = "pi> idle prompt here"
    tail_sha = hashlib.sha256(tail_text.encode()).hexdigest()
    old_state = {"t1": {"sha": tail_sha, "ts": time.time() - 600}}  # 600s ago
    state_path = tmp_path / "watchdog" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(old_state))

    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "dispatched"}}}
    terminal_read = {"result": {"buffer": tail_text}}
    fake = _FakeSubprocess([dispatch_show, ("_term", terminal_read)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    # quiet_s=300, age=600 > 300 → QUIET
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=state_path,
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 1  # QUIET → exit 1
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["dispatches"][0]["state"] == "QUIET"


def test_classify_ok(tmp_path, monkeypatch):
    """No anomaly → OK."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "dispatched"}}}
    terminal_read = {"result": {"buffer": "working on it…"}}
    fake = _FakeSubprocess([dispatch_show, ("_term", terminal_read)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0  # OK → exit 0
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["dispatches"][0]["state"] == "OK"


# ============================================================================
# watchdog — state persistence
# ============================================================================

def test_state_persistence_across_runs(tmp_path, monkeypatch):
    """State is written after run and read on next run."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    tail_text = "pi> idle"
    expected_sha = hashlib.sha256(tail_text.encode()).hexdigest()
    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "dispatched"}}}
    terminal_read = {"result": {"buffer": tail_text}}
    fake = _FakeSubprocess([dispatch_show, ("_term", terminal_read),
                            dispatch_show, ("_term", terminal_read)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))

    state_path = tmp_path / "watchdog" / "state.json"
    report_path = tmp_path / "watchdog" / "report.json"

    # Run 1 — state is written
    watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                 state_path=state_path, report_path=report_path)
    state1 = json.loads(state_path.read_text())
    assert "t1" in state1
    assert state1["t1"]["sha"] == expected_sha

    # Run 2 — state is read from previous run (tail unchanged, age=0s → OK)
    watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                 state_path=state_path, report_path=report_path)
    state2 = json.loads(state_path.read_text())
    assert state2["t1"]["sha"] == expected_sha
    assert state2["t1"]["ts"] >= state1["t1"]["ts"]


# ============================================================================
# watchdog — exit codes
# ============================================================================

def test_exit_0_no_dead_or_quiet(tmp_path, monkeypatch):
    """Exit 0 when only OK/COMPLETED/BLOCKED rows."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
        {"event": "dispatch", "route": "builder", "task_id": "t2",
         "terminal": "term_y", "dispatch_id": "d2", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    dispatch_show_completed = {"result": {"dispatch": {"id": "d1", "status": "completed"}}}
    terminal_read_ok = {"result": {"buffer": "working"}}
    dispatch_show_ok = {"result": {"dispatch": {"id": "d2", "status": "dispatched"}}}
    fake = _FakeSubprocess([dispatch_show_completed, ("_term", terminal_read_ok),
                            dispatch_show_ok, ("_term", terminal_read_ok)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0


def test_exit_1_when_dead_present(tmp_path, monkeypatch):
    """Exit 1 when any DEAD row."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_gone", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    fake = _FakeSubprocess([{"result": {"dispatch": {"id": "d1", "status": "dispatched"}}},
                            ("_raise", "terminal gone")])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 1


# ============================================================================
# watchdog — empty / missing ledger
# ============================================================================

def test_empty_ledger(tmp_path, monkeypatch):
    """Empty ledger → exit 0, no report rows."""
    (tmp_path / "dispatch_ledger.jsonl").write_text("")
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["rows"] == 0
    assert report["dead_or_quiet"] == 0


def test_ledger_missing_file(tmp_path, monkeypatch):
    """Missing ledger file → exit 0."""
    rc = watchdog_run(300, 3600, ledger=tmp_path / "nonexistent.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0


# ============================================================================
# watchdog — quiet_s boundary
# ============================================================================

def test_quiet_not_triggered_if_below_threshold(tmp_path, monkeypatch):
    """Tail unchanged but age < quiet_s → still OK (not QUIET)."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    tail_text = "pi> idle"
    tail_sha = hashlib.sha256(tail_text.encode()).hexdigest()
    old_state = {"t1": {"sha": tail_sha, "ts": time.time() - 30}}  # only 30s
    state_path = tmp_path / "watchdog" / "state.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(old_state))

    dispatch_show = {"result": {"dispatch": {"id": "d1", "status": "dispatched"}}}
    terminal_read = {"result": {"buffer": tail_text}}
    fake = _FakeSubprocess([dispatch_show, ("_term", terminal_read)])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=state_path,
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0  # Not QUIET yet, so exit 0
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["dispatches"][0]["state"] == "OK"


# ============================================================================
# watchdog — already resolved dispatches excluded
# ============================================================================

def test_dispatches_with_wait_result_rc0_are_excluded(tmp_path, monkeypatch):
    """Dispatches that have a wait_result with rc=0 are not candidates."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
        {"event": "wait_result", "task_id": "t1", "dispatch_id": "d1",
         "rc": 0, "ts": "2026-08-26T00:05:00+00:00"},
    ])
    rc = watchdog_run(300, 3600, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0
    report = json.loads((tmp_path / "watchdog" / "report.json").read_text())
    assert report["rows"] == 0


# ============================================================================
# watchdog — terminal timeout
# ============================================================================

def test_cli_flags_wired(tmp_path, monkeypatch):
    """CLI flags are parsed and passed to run()."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
    ])
    fake = _FakeSubprocess([{"result": {"dispatch": {"id": "d1", "status": "completed"}}},
                            ("_term", {"result": {"buffer": "pi>"}})])
    monkeypatch.setattr(watchdog, "subprocess", _ModuleStub(fake))
    # --quiet-s 600 --max-age-s 7200 passed through
    rc = watchdog_run(600, 7200, ledger=tmp_path / "dispatch_ledger.jsonl",
                      state_path=tmp_path / "watchdog/state.json",
                      report_path=tmp_path / "watchdog/report.json")
    assert rc == 0


# ============================================================================
# ledger_stats — aggregation arithmetic
# ============================================================================

def test_stats_aggregation(tmp_path):
    """Per-route counts and rates computed correctly."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "builder", "task_id": "t1",
         "terminal": "term_x", "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00", "usd_per_m_in": 1.5, "usd_per_m_out": 3.0},
        {"event": "wait_result", "task_id": "t1", "dispatch_id": "d1",
         "rc": 0, "ts": "2026-08-26T00:05:00+00:00"},
        {"event": "dispatch", "route": "builder", "task_id": "t2",
         "terminal": "term_y", "dispatch_id": "d2", "spec_head": "test",
         "ts": "2026-08-26T00:10:00+00:00", "usd_per_m_in": 2.0, "usd_per_m_out": 1.0},
        {"event": "wait_result", "task_id": "t2", "dispatch_id": "d2",
         "rc": 1, "ts": "2026-08-26T00:15:00+00:00"},
        {"event": "dispatch", "route": "scout", "task_id": "t3",
         "terminal": "term_z", "dispatch_id": "d3", "spec_head": "scout",
         "ts": "2026-08-26T00:20:00+00:00", "usd_per_m_in": 0.5, "usd_per_m_out": 0.5},
    ])
    rc = ledger_stats_run(ledger=tmp_path / "dispatch_ledger.jsonl",
                          output=tmp_path / "routing_stats.json")
    assert rc == 0

    stats = json.loads((tmp_path / "routing_stats.json").read_text())
    routes = {r["route"]: r for r in stats["routes"]}

    # builder: 2 dispatches, 1 completed (rc=0), fpr=50%, mean_rc=0.5
    b = routes["builder"]
    assert b["n_dispatches"] == 2
    assert b["n_completed"] == 1
    assert b["first_pass_rate"] == "50.0%"
    assert b["mean_wait_rc"] == "0.50"
    assert b["mean_cost_usd_delta"] == "$3.7500"  # (1.5+3.0 + 2.0+1.0) / 2

    # scout: 1 dispatch, 0 completed (no wait_result)
    s = routes["scout"]
    assert s["n_dispatches"] == 1
    assert s["n_completed"] == 0
    assert s["mean_wait_rc"] == "N/A"


def test_stats_missing_fields_graceful(tmp_path):
    """Missing route, cost, rc fields don't crash aggregation."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "task_id": "t1", "dispatch_id": "d1",
         "spec_head": "test", "ts": "2026-08-26T00:00:00+00:00"},
    ])
    rc = ledger_stats_run(ledger=tmp_path / "dispatch_ledger.jsonl",
                          output=tmp_path / "routing_stats.json")
    assert rc == 0
    stats = json.loads((tmp_path / "routing_stats.json").read_text())
    assert len(stats["routes"]) == 1
    r = stats["routes"][0]
    assert r["route"] == "unknown"
    assert r["n_dispatches"] == 1
    assert r["n_completed"] == 0
    assert r["mean_cost_usd_delta"] == "N/A"


def test_stats_empty_ledger(tmp_path):
    """Empty ledger → no crash."""
    (tmp_path / "dispatch_ledger.jsonl").write_text("")
    rc = ledger_stats_run(ledger=tmp_path / "dispatch_ledger.jsonl",
                          output=tmp_path / "routing_stats.json")
    assert rc == 0
    stats = json.loads((tmp_path / "routing_stats.json").read_text())
    assert stats["rows"] == 0


def test_stats_no_ledger_file(tmp_path):
    """Missing ledger → no crash."""
    rc = ledger_stats_run(ledger=tmp_path / "nonexistent.jsonl",
                          output=tmp_path / "routing_stats.json")
    assert rc == 0


def test_first_pass_rate_100_percent(tmp_path):
    """100% first-pass rate."""
    _write_ledger(tmp_path / "dispatch_ledger.jsonl", [
        {"event": "dispatch", "route": "super", "task_id": "t1",
         "dispatch_id": "d1", "spec_head": "test",
         "ts": "2026-08-26T00:00:00+00:00"},
        {"event": "wait_result", "task_id": "t1", "dispatch_id": "d1",
         "rc": 0, "ts": "2026-08-26T00:05:00+00:00"},
        {"event": "dispatch", "route": "super", "task_id": "t2",
         "dispatch_id": "d2", "spec_head": "test",
         "ts": "2026-08-26T00:10:00+00:00"},
        {"event": "wait_result", "task_id": "t2", "dispatch_id": "d2",
         "rc": 0, "ts": "2026-08-26T00:15:00+00:00"},
    ])
    rc = ledger_stats_run(ledger=tmp_path / "dispatch_ledger.jsonl",
                          output=tmp_path / "routing_stats.json")
    assert rc == 0
    stats = json.loads((tmp_path / "routing_stats.json").read_text())
    assert stats["routes"][0]["first_pass_rate"] == "100.0%"


# ============================================================================
# Monkeypatch helper: wrap subprocess module
# ============================================================================

class _ModuleStub:
    """Replace an entire module with a namespace where .run is our fake."""
    def __init__(self, fake_run):
        self.run = fake_run
        # Expose the exception classes so `except subprocess.TimeoutExpired` still works
        self.TimeoutExpired = subprocess.TimeoutExpired
        self.CalledProcessError = subprocess.CalledProcessError