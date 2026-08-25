#!/usr/bin/env python3
"""Deterministic stuck-worker watchdog — report-only, shadow-mode (never stops workers).

Reads adw_data/dispatch_ledger.jsonl, selects dispatches with a dispatch event
but no corresponding wait_result with rc=0. For each candidate, runs two orca
subprocess calls (timeout <= 20s) and classifies: COMPLETED, BLOCKED, DEAD,
QUIET, or OK. State (tail sha256 + timestamp) persists across runs.
Exit 1 if any DEAD or QUIET row, else 0.

Usage:
  python3 tools/watchdog.py
  python3 tools/watchdog.py --quiet-s 600 --max-age-s 7200
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "adw_data" / "dispatch_ledger.jsonl"
STATE_PATH = REPO_ROOT / "adw_data" / "watchdog" / "state.json"
REPORT_PATH = REPO_ROOT / "adw_data" / "watchdog" / "report.json"

# Patterns that signal a worker is waiting for coordinator input (BLOCKED).
BLOCKED_RE = re.compile(
    r"(question|approval|missing.info|environment.blocked|structural|"
    r"blocked|escalation|ask.you|waiting.for|need.confirm|confirm|"
    r"orca orchestration ask|orca orchestration send)"
)

GONE_MARKERS = ("not found", "terminal gone", "no such terminal",
                "terminal does not exist", "connection refused")


def _load_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def _candidates(rows: list[dict]) -> list[dict]:
    """Return dispatch rows whose (task_id, dispatch_id) has no rc=0 wait_result."""
    completed: set[tuple[str, str]] = set()
    dispatches: dict[tuple[str, str], dict] = {}
    for r in rows:
        tid = r.get("task_id", "")
        did = r.get("dispatch_id", "")
        if not tid or not did:
            continue
        key = (tid, did)
        if r.get("event") == "dispatch":
            dispatches[key] = r
        elif r.get("event") == "wait_result" and r.get("rc") == 0:
            completed.add(key)
    return [d for k, d in dispatches.items() if k not in completed]


def _load_state(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state))


def _orca_dispatch_show(task_id: str) -> dict:
    """Run orca orchestration dispatch-show --task <id> --json, timeout 20s."""
    try:
        r = subprocess.run(
            ["orca", "orchestration", "dispatch-show", "--task", task_id, "--json"],
            capture_output=True, text=True, timeout=20,
        )
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return {}


def _orca_terminal_read(term_handle: str) -> dict | None:
    """Run orca terminal read --terminal <handle> --json, timeout 20s.
    Returns parsed dict or None on failure."""
    if not term_handle:
        return None
    try:
        r = subprocess.run(
            ["orca", "terminal", "read", "--terminal", term_handle, "--json"],
            capture_output=True, text=True, timeout=20,
        )
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except (subprocess.TimeoutExpired, json.JSONDecodeError, OSError):
        return None


def _terminal_tail(term_result: dict | None) -> str:
    """Extract tail text from terminal read result."""
    if term_result is None:
        return ""
    res = term_result.get("result") or term_result
    for key in ("buffer", "tail", "content", "output"):
        val = res.get(key)
        if isinstance(val, str) and val:
            return val[-2000:]
    return ""


def _dispatch_status(orca_result: dict) -> str:
    """Extract dispatch status from dispatch-show result, tolerating shapes."""
    if not orca_result:
        return ""
    disp = orca_result.get("result") or orca_result
    if isinstance(disp, dict) and "dispatch" in disp:
        disp = disp["dispatch"]
    return disp.get("status", "") if isinstance(disp, dict) else ""


def _classify(disp: dict, orca_status: str, tail: str, tail_sha: str,
              state: dict, quiet_s: int, max_age_s: int) -> tuple[str, str]:
    """Classify a dispatch purely from evidence. Returns (state, evidence)."""
    task_id = disp.get("task_id", "")
    term = disp.get("terminal", "")

    # COMPLETED: orca says completed (only terminal state)
    if orca_status == "completed":
        return "COMPLETED", "orca dispatch status=completed"

    # DEAD: terminal read failed (empty tail) or terminal gone, still dispatched
    if not tail or _is_terminal_gone(tail):
        if orca_status in ("dispatched", ""):
            evidence = f"terminal dead/gone, orca status={orca_status!r}"
            if term:
                evidence += f", handle={term}"
            return "DEAD", evidence

    # BLOCKED: tail matches question/approval/blocked patterns
    if tail and BLOCKED_RE.search(tail.lower()):
        return "BLOCKED", "terminal tail matches question/blocked patterns"

    # QUIET: tail sha unchanged from previous run AND age of stored sha > quiet_s
    now = time.time()
    prev = state.get(task_id) or {}
    prev_sha = prev.get("sha", "")
    prev_ts = prev.get("ts", 0)
    if tail_sha and prev_sha and tail_sha == prev_sha:
        age = now - prev_ts
        if age > quiet_s:
            return "QUIET", f"tail unchanged for {age:.0f}s (sha stored {prev_ts:.0f})"

    # OK
    age_s = now - disp.get("_dispatch_ts", now)
    if age_s > max_age_s:
        return "OK", f"still dispatched, age {age_s:.0f}s > max_age_s ({max_age_s}s)"
    return "OK", "no anomaly detected"


def _is_terminal_gone(tail: str) -> bool:
    """Heuristic: terminal is gone if tail carries explicit gone markers."""
    lower = tail.lower()
    return any(m in lower for m in GONE_MARKERS)


def _playbook(state_label: str) -> str:
    if state_label == "DEAD":
        return "adws/playbooks/dispatch_recovery.md §3"
    if state_label == "QUIET":
        return "adws/playbooks/dispatch_recovery.md §3 (silent-done)"
    if state_label == "BLOCKED":
        return "adws/playbooks/escalation_triage.md"
    return ""


def _parse_ts(ts_str: str, fallback: float) -> float:
    if ts_str:
        try:
            return datetime.fromisoformat(ts_str).timestamp()
        except (ValueError, OSError):
            pass
    return fallback


def run(quiet_s: int, max_age_s: int, *, ledger: Path = LEDGER,
        state_path: Path = STATE_PATH, report_path: Path = REPORT_PATH) -> int:
    """Core watchdog run. Returns exit code (1 if any DEAD/QUIET, else 0)."""
    rows = _load_ledger(ledger)
    candidates = _candidates(rows)
    if not candidates:
        print("No active (unresolved) dispatches found.")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({"dispatches": [], "rows": 0, "dead_or_quiet": 0}))
        return 0

    now = time.time()
    state = _load_state(state_path)
    new_state: dict = {}
    results: list[dict] = []
    dead_or_quiet = 0

    for disp in candidates:
        task_id = disp.get("task_id", "")
        term = disp.get("terminal", "")

        disp_ts = _parse_ts(disp.get("ts", ""), now)
        disp["_dispatch_ts"] = disp_ts

        orca_result = _orca_dispatch_show(task_id)
        orca_status = _dispatch_status(orca_result)

        term_result = _orca_terminal_read(term) if term else None
        tail = _terminal_tail(term_result)
        tail_sha = hashlib.sha256(tail.encode()).hexdigest() if tail else ""

        label, evidence = _classify(disp, orca_status, tail, tail_sha,
                                    state, quiet_s, max_age_s)

        if tail_sha:
            new_state[task_id] = {"sha": tail_sha, "ts": now}

        age_s = round(now - disp_ts)
        quiet_s_val = "N/A"
        if tail_sha:
            prev = state.get(task_id) or {}
            if tail_sha == prev.get("sha", ""):
                quiet_s_val = str(round(now - prev.get("ts", now)))
            else:
                quiet_s_val = "0"

        pb = _playbook(label)
        if label in ("DEAD", "QUIET"):
            dead_or_quiet += 1

        results.append({
            "dispatch_id": disp.get("dispatch_id", ""),
            "task_id": task_id,
            "state": label,
            "quiet_s": quiet_s_val,
            "age_s": age_s,
            "evidence": evidence,
            "playbook": pb,
        })

    _save_state(state_path, new_state)

    fmt = "{:<38} {:<12} {:>8} {:>8}  {}"
    print(fmt.format("DISPATCH", "STATE", "QUIET_S", "AGE_S", "EVIDENCE"))
    print("-" * 90)
    for r in results:
        print(fmt.format(r["dispatch_id"], r["state"], r["quiet_s"],
                         r["age_s"], r["evidence"]))
        if r["playbook"]:
            print(f"  → {r['playbook']}")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({
        "dispatches": results,
        "rows": len(results),
        "dead_or_quiet": dead_or_quiet,
    }, indent=2))

    return 1 if dead_or_quiet else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Stuck-worker watchdog (report-only)")
    parser.add_argument("--quiet-s", type=int, default=300,
                        help="seconds of tail silence before QUIET classification (default 300)")
    parser.add_argument("--max-age-s", type=int, default=3600,
                        help="max dispatch age before annotation (default 3600)")
    args = parser.parse_args()
    return run(args.quiet_s, args.max_age_s)


if __name__ == "__main__":
    sys.exit(main())