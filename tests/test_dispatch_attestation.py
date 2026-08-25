"""Receipt attestation + envelope correlation for the dispatch pipeline.

Mock subprocess and the Orca-facing helpers — NO live orca/API calls.
"""
import argparse
import json
import sys
from pathlib import Path
from unittest import mock

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TOOLS = REPO_ROOT / "tools"
sys.path.insert(0, str(TOOLS))

import orca_dispatch as od  # noqa: E402

FAKE_ROUTES = {
    "claude": {"backend": "claude-cli", "model": "claude-fable-5"},
    "builder": {"backend": "pi-openrouter", "model": "deepseek/deepseek-v4-pro"},
}


def _args(**overrides) -> argparse.Namespace:
    base = dict(route="claude", spec="do the thing", json=None,
                worktree="current", dry_run=False, terminal=None,
                wait=False, timeout=3600)
    base.update(overrides)
    return argparse.Namespace(**base)


def _receipt(requested_model="claude-fable-5", effective_model="claude-fable-5",
             effective_agent="claude", omit_effective=False):
    launch = {"requested": {"agent": "claude", "model": requested_model}}
    if not omit_effective:
        launch["effective"] = {"agent": effective_agent, "model": effective_model}
    return json.dumps({"launch": launch})


@pytest.fixture
def mocks(tmp_path, monkeypatch):
    """Route all filesystem writes into tmp_path and stub Orca + ledger."""
    monkeypatch.setattr(od, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(od, "load_sssf_config",
                        lambda: {"routes": FAKE_ROUTES})
    monkeypatch.setattr(od, "_task_create", lambda spec, dry_run: "task_123")
    ledger = []
    monkeypatch.setattr(od, "_ledger", lambda rec: ledger.append(rec))
    # git rev-parse inside _dispatch_meta
    fake_cp = type("CP", (), {"returncode": 0, "stdout": "deadbeef\n", "stderr": ""})()
    monkeypatch.setattr(od.subprocess, "run", lambda *a, **k: fake_cp)
    return {"ledger": ledger, "tmp": tmp_path}


def _worker_start_result():
    return {"ok": True, "result": {"dispatch": {"id": "disp_123"}}}


def test_receipt_match_records_ledger_and_receipt_file(mocks):
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as mp:
        mp.setattr(od, "_orca", lambda *a, **k: _worker_start_result())
        rc = od.cmd_run(_args(json=_receipt()))

    assert rc == 0
    ledger = mocks["ledger"]
    assert ledger[0]["event"] == "dispatch"
    assert ledger[0]["receipt"]["requested"] == {
        "agent": "claude", "model": "claude-fable-5"}
    assert ledger[0]["receipt"]["effective"] == {
        "agent": "claude", "model": "claude-fable-5"}
    assert ledger[0]["receipt"]["receipt_sha256"]  # non-empty
    # raw receipt saved
    receipt_file = mocks["tmp"] / "adw_data" / "receipts" / "disp_123.json"
    assert receipt_file.is_file()
    assert json.loads(receipt_file.read_text())["launch"]["effective"]["model"] \
        == "claude-fable-5"


def test_receipt_mismatch_exits_nonzero_before_work(mocks):
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as mp:
        mp.setattr(od, "_orca",
                   lambda *a, **k: pytest.fail("_orca must not be called on mismatch"))
        with pytest.raises(SystemExit) as exc:
            od.cmd_run(_args(json=_receipt(effective_model="claude-fable-6")))

    assert exc.value.code != 0
    ledger = mocks["ledger"]
    assert ledger[0]["event"] == "launch_rejected"
    assert ledger[0]["receipt_effective_model"] == "claude-fable-6"


def test_missing_receipt_blocks(mocks):
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as mp:
        mp.setattr(od, "_orca",
                   lambda *a, **k: pytest.fail("_orca must not be called without receipt"))
        with pytest.raises(SystemExit) as exc:
            od.cmd_run(_args(json=None))

    assert exc.value.code != 0


def test_missing_effective_model_proceeds(mocks):
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as mp:
        mp.setattr(od, "_orca", lambda *a, **k: _worker_start_result())
        rc = od.cmd_run(_args(json=_receipt(omit_effective=True)))

    assert rc == 0
    ledger = mocks["ledger"]
    assert ledger[0]["event"] == "dispatch"
    assert ledger[0]["receipt"]["effective"] == {}


def test_dispatch_meta_content(mocks):
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as mp:
        mp.setattr(od, "_orca", lambda *a, **k: _worker_start_result())
        od.cmd_run(_args(json=_receipt()))

    meta_file = mocks["tmp"] / "adw_data" / "dispatches" / "disp_123" / \
        "dispatch_meta.json"
    assert meta_file.is_file()
    meta = json.loads(meta_file.read_text())
    assert meta["task_id"] == "task_123"
    assert meta["dispatch_id"] == "disp_123"
    assert meta["attempt"] == 1
    assert meta["route"] == "claude"
    assert meta["model"] == "claude-fable-5"
    assert meta["spec_sha256"]  # non-empty
    assert meta["base_sha"] == "deadbeef"


def test_pi_path_preflight_only_marker(mocks):
    monkeypatch = pytest.MonkeyPatch()
    with monkeypatch.context() as mp:
        # pi path: terminal create -> wait -> dispatch
        mp.setattr(od, "_orca", mock.Mock(side_effect=[
            {"ok": True, "result": {"terminal": {"handle": "term_x"}}},
            {"ok": True},
            {"ok": True, "result": {"dispatch": {"id": "disp_pi"}}},
        ]))
        with mock.patch("model_preflight.check", return_value=(True, "OK")):
            rc = od.cmd_run(_args(route="builder"))

    assert rc == 0
    ledger = mocks["ledger"]
    assert ledger[0]["receipt"] == {"mode": "preflight_only"}
