"""Tests for tools/fanout.py and tools/probe.py hardening.

Covers audit findings:
  F46 — alias filename collision resolution
  F49 — transient vs non-transient retry classification
  F50 — concurrency cap arithmetic
  F64 — probe pass/fail rule (sentinel AND exit code 0)
  F65 — probe targets generated from sssf.config.yaml routes
"""
from __future__ import annotations

import os
import sys
import urllib.error

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(REPO_ROOT, "tools")
sys.path.insert(0, TOOLS)

import fanout  # noqa: E402
import probe  # noqa: E402


# ---- F46: alias filename collision resolution ------------------------------

def test_resolve_filenames_no_collision():
    results = [
        {"route": "builder", "alias": "Builder-1/Flux"},
        {"route": "scout", "alias": "Scout/Wisp"},
    ]
    fname_map = fanout._resolve_filenames(results)
    assert fname_map["builder"] == "Builder-1_Flux"
    assert fname_map["scout"] == "Scout_Wisp"


def test_resolve_filenames_collision_appends_hash():
    # "Same/Name" and "Same_Name" both sanitize to "Same_Name".
    results = [
        {"route": "route_a", "alias": "Same/Name"},
        {"route": "route_b", "alias": "Same_Name"},
    ]
    fname_map = fanout._resolve_filenames(results)
    a, b = fname_map["route_a"], fname_map["route_b"]
    assert a != b, "colliding aliases must never share a filename"
    assert a.startswith("Same_Name_") and b.startswith("Same_Name_")
    # hash suffix is 6 hex chars
    assert len(a) == len("Same_Name_") + 6
    assert len(b) == len("Same_Name_") + 6


def test_resolve_filenames_collision_stable_hash():
    # Same route always maps to the same hashed filename (deterministic).
    results = [
        {"route": "route_a", "alias": "Same/Name"},
        {"route": "route_b", "alias": "Same_Name"},
    ]
    m1 = fanout._resolve_filenames(results)
    m2 = fanout._resolve_filenames(results)
    assert m1 == m2


# ---- F49: transient vs non-transient retry classification ------------------

def test_is_transient_error_http_codes():
    for code in (429, 500, 502, 503, 504, 599):
        exc = urllib.error.HTTPError("http://x", code, "err", None, None)
        assert fanout._is_transient_error(exc), f"code {code} should be transient"
    for code in (400, 401, 403, 404, 422):
        exc = urllib.error.HTTPError("http://x", code, "err", None, None)
        assert not fanout._is_transient_error(exc), f"code {code} should NOT be transient"


def test_is_transient_error_urlerror():
    assert fanout._is_transient_error(urllib.error.URLError("timed out"))
    assert fanout._is_transient_error(urllib.error.URLError("connection refused"))


def test_is_transient_error_other_exception_is_not_transient():
    assert not fanout._is_transient_error(ValueError("bad json"))
    assert not fanout._is_transient_error(KeyError("choices"))


def test_call_route_retries_once_on_transient(monkeypatch):
    calls = []

    def fake_request(path, payload, timeout=120):
        calls.append(path)
        if len(calls) == 1:
            raise urllib.error.URLError("timed out")
        return {"choices": [{"message": {"content": "hi"}}], "model": "m",
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    monkeypatch.setattr(fanout, "request", fake_request)
    monkeypatch.setattr(fanout.time, "sleep", lambda s: None)
    target = {"route": "r", "alias": "a", "model": "m",
              "config": {"backend": "openrouter-api"}}
    result = fanout._call_route(target, "prompt", None, timeout=120)
    assert result["status"] == "PASS"
    assert len(calls) == 2, "transient error must be retried once"


def test_call_route_no_retry_on_non_transient(monkeypatch):
    calls = []

    def fake_request(path, payload, timeout=120):
        calls.append(path)
        raise urllib.error.HTTPError("http://x", 400, "Bad Request", None, None)

    monkeypatch.setattr(fanout, "request", fake_request)
    monkeypatch.setattr(fanout.time, "sleep", lambda s: None)
    target = {"route": "r", "alias": "a", "model": "m",
              "config": {"backend": "openrouter-api"}}
    result = fanout._call_route(target, "prompt", None, timeout=120)
    assert result["status"] == "FAIL"
    assert len(calls) == 1, "non-transient error must fail immediately"


# ---- F50: concurrency cap arithmetic ---------------------------------------

def test_concurrency_cap():
    # max_workers = min(len(targets), cap), cap defaults to 4
    assert fanout._max_workers(0) == 0
    assert fanout._max_workers(1) == 1
    assert fanout._max_workers(3) == 3
    assert fanout._max_workers(4) == 4
    assert fanout._max_workers(10) == 4
    assert fanout._max_workers(100) == 4
    # explicit cap
    assert fanout._max_workers(10, 2) == 2
    assert fanout._max_workers(1, 8) == 1


# ---- F64: probe pass/fail rule (sentinel AND exit code 0) ------------------

class _FakeResult:
    def __init__(self, returncode, stdout, stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_target():
    return {"argv": ["echo", "m", probe.PROMPT], "model": "m", "env": None}


def test_probe_passes_sentinel_and_exit_zero(monkeypatch):
    def fake_run(argv, env=None, capture_output=True, text=True, timeout=None):
        return _FakeResult(0, probe.SENTINEL + " response")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.probe("route", _make_target(), None, 120)
    assert result["pass"] is True


def test_probe_fails_missing_sentinel(monkeypatch):
    def fake_run(argv, env=None, capture_output=True, text=True, timeout=None):
        return _FakeResult(0, "some other output")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.probe("route", _make_target(), None, 120)
    assert result["pass"] is False


def test_probe_fails_nonzero_exit_with_sentinel(monkeypatch):
    # Sentinel present but subprocess crashed: still FAIL.
    def fake_run(argv, env=None, capture_output=True, text=True, timeout=None):
        return _FakeResult(1, probe.SENTINEL + " but crashed", "error")

    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    result = probe.probe("route", _make_target(), None, 120)
    assert result["pass"] is False


# ---- F#5: --system-text / --system-file / legacy --system -----------------

def test_read_system_legacy_text(tmp_path):
    # A non-path string is treated as literal text.
    assert fanout._read_system("be concise") == "be concise"


def test_read_system_legacy_existing_path(tmp_path):
    f = tmp_path / "sys.txt"
    f.write_text("from file", encoding="utf-8")
    # Existing path is read as a file (path-then-text semantics).
    assert fanout._read_system(str(f)) == "from file"


def test_read_system_file_explicit(tmp_path):
    f = tmp_path / "sys.txt"
    f.write_text("from file", encoding="utf-8")
    assert fanout._read_system_file(str(f)) == "from file"


# ---- F65: probe targets generated from sssf.config.yaml --------------------

def test_build_targets_from_config():
    config = probe._load_config()
    targets = probe._build_targets(config)
    # session routes are non-callable and must be excluded
    assert "planner" not in targets
    assert "reviewer" not in targets
    # callable routes are present
    assert "builder" in targets
    assert "scout" in targets
    assert "documenter" in targets
    # every target has an argv template, model, and env (possibly None)
    for name, tgt in targets.items():
        assert isinstance(tgt["argv"], list) and tgt["argv"]
        assert tgt["model"]
        assert "env" in tgt
        # no orphaned {role_prompt}-introducing flags left behind
        for i, a in enumerate(tgt["argv"]):
            if a in ("-s", "--append-system-prompt"):
                assert i + 1 < len(tgt["argv"]), f"orphaned flag {a!r} in {name}"
            assert "{role_prompt}" not in a
            assert "{model}" not in a
            assert "{prompt}" not in a


def test_build_targets_openrouter_api_argv_wellformed():
    config = probe._load_config()
    targets = probe._build_targets(config, route_filter={"documenter"})
    argv = targets["documenter"]["argv"]
    # -s {role_prompt} pair must be fully dropped, leaving -m <model> <prompt>
    assert "-s" not in argv
    assert argv[-1] == probe.PROMPT
    assert "-m" in argv
