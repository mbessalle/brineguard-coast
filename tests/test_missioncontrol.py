"""Tests for BrineGuard Mission Control (server parsers + HTTP integration)."""
import importlib.util
import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAIM_IDS = [f"C{i}" for i in range(1, 7)]


def _load_server():
    spec = importlib.util.spec_from_file_location(
        "missioncontrol_server", REPO / "app" / "missioncontrol" / "server.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


server = _load_server()


# --------------------------------------------------------------------------
# Parser unit tests
# --------------------------------------------------------------------------

def test_parse_claims_returns_all_canonical_ids():
    claims = server.parse_claims()
    assert [c["id"] for c in claims] == CLAIM_IDS
    for c in claims:
        assert isinstance(c["text"], str) and len(c["text"]) > 20


def test_parse_claims_text_is_markdown_free():
    claims = server.parse_claims()
    assert all("*" not in c["text"] for c in claims)
    assert any("18.6" in c["text"] for c in claims)  # C1 headline figure present


def test_parse_summary_has_required_keys():
    summary = server.parse_summary()
    assert set(summary) >= {"project", "phases", "headline", "freeze_commit"}


def test_parse_headline_subkeys():
    headline = server.parse_headline()
    assert set(headline) == {"steady", "tidal", "ensemble_min_capacity", "ensemble_min_cost"}
    for v in headline.values():
        assert isinstance(v, str) and v.endswith("%")


def test_parse_headline_values_match_frozen_evidence():
    headline = server.parse_headline()
    assert headline["steady"] == "18.6–20.3%"
    assert headline["tidal"] == "19.4–20.9%"
    assert headline["ensemble_min_capacity"] == "14.5%"
    assert headline["ensemble_min_cost"] == "16.1%"


def test_parse_project_and_freeze_commit():
    assert server.parse_project() == "BrineGuard Coast"
    assert server.parse_freeze_commit() == "41ffc83"


def test_parse_phases_has_six_phases():
    phases = server.parse_phases()
    assert len(phases) == 6
    assert phases[0]["id"] == "Phase 0"
    assert phases[-1]["id"] == "Phase 5"
    assert all(p["name"] for p in phases)


def test_parse_runs_lists_all_run_dirs():
    runs = server.parse_runs()
    names = {r["name"] for r in runs}
    assert "phase1-validation" in names
    assert "phase4-ensemble-v2" in names
    for r in runs:
        assert r["status"] in {"complete", "failed", "unknown"}


# --------------------------------------------------------------------------
# HTTP integration test
# --------------------------------------------------------------------------

def test_server_integration():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, str(REPO / "app" / "missioncontrol" / "server.py"),
         "--port", str(port)],
        cwd=REPO, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        summary = claims = index = None
        for _ in range(40):
            time.sleep(0.25)
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/summary", timeout=2) as r:
                    summary = json.load(r)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/api/claims", timeout=2) as r:
                    claims = json.load(r)
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{port}/", timeout=2) as r:
                    index = r.read().decode()
                break
            except Exception:
                continue

        assert summary is not None, "server never answered /api/summary"
        assert set(summary) >= {"project", "phases", "headline", "freeze_commit"}
        assert set(summary["headline"]) == {
            "steady", "tidal", "ensemble_min_capacity", "ensemble_min_cost",
        }
        assert {c["id"] for c in claims} == set(CLAIM_IDS)
        assert "BrineGuard" in index
    finally:
        proc.terminate()
        proc.wait(timeout=5)
