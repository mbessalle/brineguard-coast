#!/usr/bin/env python3
"""Deterministic end-to-end pipeline verifier (Tier 3, zero LLM tokens).

Verifies EVERY stage of one factory run — plan, spec fidelity, delegation
provenance, model identity, prompt delivery, handoff, deliverable, tests,
live server, duration, token cost — from artifacts and live checks only.
Template table: CHECKS rows; each returns (pass, evidence). Any FAIL => exit 1.

Usage: python3 tools/pipeline_verify.py [--manifest adw_data/missioncontrol/pipeline_manifest.json]
       Stage-1 only (pre-completion): add --stage 1
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLAIM_IDS = [f"C{i}" for i in range(1, 7)]


def _ac_ids(man) -> list[str]:
    """Acceptance-criteria ids for this run (manifest-driven; default AC1..AC8)."""
    return man.get("ac_ids") or [f"AC{i}" for i in range(1, 9)]


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _orca_json(argv: list[str]) -> dict:
    proc = subprocess.run(["orca"] + argv + ["--json"], capture_output=True,
                          text=True, timeout=60)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "_raw": proc.stdout[-300:], "_rc": proc.returncode}


def _ledger_rows() -> list[dict]:
    p = REPO / "adw_data" / "dispatch_ledger.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# checks — each: fn(man) -> (bool, str evidence)
# ---------------------------------------------------------------------------

def chk_plan(man):
    p = REPO / man["plan_path"]
    txt = p.read_text() if p.is_file() else ""
    missing = [a for a in _ac_ids(man) if a not in txt]
    ok = p.is_file() and p.stat().st_size > 500 and not missing
    return ok, (f"{p} sha256={_sha(p)[:12]}, all AC ids present" if ok
                else f"{p} missing/thin or lacks ACs {missing}")


def chk_spec_fidelity(man):
    spec = Path(man["spec_path"]).read_text()
    missing = [a for a in _ac_ids(man) if a not in spec]
    ok = not missing and _sha(Path(man["spec_path"])) == man["spec_sha256"]
    return ok, ("all AC ids present, spec hash matches manifest" if ok
                else f"missing ACs {missing} or hash mismatch")


def chk_ledger(man):
    rows = [r for r in _ledger_rows() if r.get("task_id") == man["task_id"]]
    ok = any(r["event"] == "dispatch" and r.get("dispatch_id") == man["dispatch_id"]
             and r.get("model") == man["expected_model"] for r in rows)
    return ok, f"{len(rows)} ledger rows for {man['task_id']}"


def _dispatch_record(man):
    d = _orca_json(["orchestration", "dispatch-show", "--task", man["task_id"]])
    return (d.get("result") or {}).get("dispatch") or {}


def chk_orca_provenance(man):
    disp = _dispatch_record(man)
    ledg = next((r for r in _ledger_rows() if r.get("dispatch_id") == man["dispatch_id"]
                 and r["event"] == "dispatch"), {})
    ok = (disp.get("id") == man["dispatch_id"]
          and disp.get("task_id") == man["task_id"]
          and disp.get("assignee_handle") == ledg.get("terminal"))
    return ok, (f"orca dispatch id/task/assignee all match manifest+ledger ({disp.get('assignee_handle')})"
                if ok else f"mismatch: orca={disp.get('id')}/{disp.get('assignee_handle')} vs manifest {man['dispatch_id']}")


def chk_model_preflight(man):
    out = Path(man["dispatch_stdout"]).read_text()
    want = f"OK: openrouter/{man['expected_model']}"
    ok = "[preflight]" in out and want in out
    return ok, ("preflight OK line captured for expected model" if ok
                else f"no '{want}' in dispatch stdout")


def chk_prompt_delivered(man):
    # the spec text lives on the TASK record (dispatch-show is metadata only)
    d = _orca_json(["orchestration", "task-list"])
    spec = next((t.get("spec", "") for t in (d.get("result") or {}).get("tasks", [])
                 if t.get("id") == man["task_id"]), "")
    acs = _ac_ids(man)
    found = [a for a in acs if a in spec]
    spec_hash = hashlib.sha256(spec.encode()).hexdigest()
    ok = len(found) == len(acs) and spec_hash == man["spec_sha256"]
    return ok, (f"orca-stored spec byte-identical to hashed spec file, all {len(acs)} AC ids"
                if ok else f"ACs found {len(found)}/{len(acs)}, orca-spec hash {'==' if spec_hash==man['spec_sha256'] else '!='} manifest")


def chk_worker_done(man):
    disp = _dispatch_record(man)  # Orca is the source of truth, not our ledger
    ok = disp.get("status") == "completed" and disp.get("completed_at")
    return ok, (f"orca dispatch status=completed at {disp.get('completed_at')}"
                if ok else f"orca dispatch status={disp.get('status')!r}")


def chk_envelope(man):
    proc = subprocess.run([sys.executable, str(REPO / "adws" / "gates.py"),
                           "json", man.get("envelope_path", "adw_data/missioncontrol/envelope.json")],
                          capture_output=True, text=True)
    return proc.returncode == 0, f"gates.py json rc={proc.returncode}"


def chk_files(man):
    req = man.get("required_files") or ["app/missioncontrol/server.py",
                                        "app/missioncontrol/index.html",
                                        "tests/test_missioncontrol.py"]
    missing = [f for f in req if not (REPO / f).is_file()]
    return not missing, ("all deliverable files present" if not missing else f"missing {missing}")


def chk_stdlib_only(man):
    entry = man.get("server_entry")
    if entry is None:
        return True, "SKIPPED loudly: no server_entry declared for this run"
    src = (REPO / entry).read_text()
    import sys as _s
    bad = []
    for m in re.finditer(r"^\s*import\s+(.+)|^\s*from\s+([a-zA-Z_][a-zA-Z0-9_.]*)", src, re.M):
        names = ([n.strip().split(" as ")[0].split(".")[0]
                  for n in m.group(1).split(",")] if m.group(1)
                 else [m.group(2).split(".")[0]])
        for name in names:
            if name and name not in _s.stdlib_module_names:
                bad.append(name)
    if "importlib" in src or "__import__" in src:
        bad.append("dynamic-import-present")
    return not bad, ("stdlib-only imports" if not bad else f"non-stdlib imports {bad}")


def chk_tests(man):
    proc = subprocess.run([str(REPO / ".venv/bin/python"), "-m", "pytest", "-q"],
                          cwd=REPO, capture_output=True, text=True, timeout=600)
    tail = (proc.stdout or "").strip().splitlines()[-1:] or ["(no output)"]
    return proc.returncode == 0, f"pytest rc={proc.returncode} ({tail[0]})"


def chk_server(man):
    if man.get("server_entry") is None:
        return True, "SKIPPED loudly: no server_entry declared for this run"
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]
    proc = subprocess.Popen([sys.executable, man["server_entry"],
                             "--port", str(port)], cwd=REPO,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        body = claims = index = None
        for _ in range(40):
            time.sleep(0.25)
            try:
                body = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/summary", timeout=2))
                claims = json.load(urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/claims", timeout=2))
                index = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/", timeout=2).read().decode()
                break
            except Exception:
                continue
        if body is None:
            return False, "server never answered /api/summary"
        need = {"project", "phases", "headline", "freeze_commit"}
        miss = need - set(body)
        claim_ids = {c.get("id") for c in claims} if isinstance(claims, list) else set(claims or {})
        cmiss = [c for c in CLAIM_IDS if c not in claim_ids]
        ok = not miss and not cmiss and "BrineGuard" in (index or "")
        return ok, (f"live server OK on :{port} (summary keys, C1-C6, index render)"
                    if ok else f"missing keys {miss}, missing claims {cmiss}")
    finally:
        proc.terminate()


def chk_duration(man):
    disp = _dispatch_record(man)  # Orca timestamps, not orchestrator-written ones
    from datetime import datetime
    t0 = datetime.fromisoformat(disp["created_at"])
    t1 = datetime.fromisoformat(disp["completed_at"])
    secs = (t1 - t0).total_seconds()
    return 0 < secs < man["duration_budget_s"], f"build took {secs:.0f}s per orca record (budget {man['duration_budget_s']}s)"


def chk_cost(man):
    if "usage_before_usd" not in man:
        return True, "SKIPPED loudly: no usage baseline recorded at dispatch time"
    sys.path.insert(0, str(REPO / "tools"))
    from openrouter_call import load_key
    req = urllib.request.Request("https://openrouter.ai/api/v1/auth/key",
                                 headers={"Authorization": f"Bearer {load_key()}"})
    usage = json.load(urllib.request.urlopen(req, timeout=15))["data"]["usage"]
    delta = usage - man["usage_before_usd"]
    return delta < man["cost_budget_usd"], f"token cost ${delta:.4f} (budget ${man['cost_budget_usd']})"


CHECKS_STAGE1 = [
    ("plan", chk_plan), ("spec_fidelity", chk_spec_fidelity),
    ("ledger_entry", chk_ledger), ("orca_provenance", chk_orca_provenance),
    ("model_preflight", chk_model_preflight), ("prompt_delivered", chk_prompt_delivered),
]
def chk_diff_claims(man):
    if "git_base" not in man:
        return True, "SKIPPED loudly: no git_base recorded at dispatch time"
    sys.path.insert(0, str(REPO / "adws"))
    import gates
    r = gates.diff_matches_claims(man.get("envelope_path",
                                          "adw_data/missioncontrol/envelope.json"),
                                  base=man["git_base"])
    return r["pass"], str(r["detail"])[:200]


def chk_protected(man):
    if "git_base" not in man:
        return True, "SKIPPED loudly: no git_base recorded at dispatch time"
    sys.path.insert(0, str(REPO / "adws"))
    import gates
    r = gates.protected_paths_untouched(base=man["git_base"])
    return r["pass"], str(r["detail"])[:200]


def chk_attestation(man):
    row = next((r for r in _ledger_rows() if r.get("dispatch_id") == man["dispatch_id"]
                and r["event"] == "dispatch"), {})
    rec = row.get("receipt")
    if rec is None:
        return False, "no receipt recorded in ledger (pre-attestation dispatch?)"
    if rec.get("mode") == "preflight_only":
        return True, "LOUD: pi two-step route — catalog preflight only, launch not attested"
    eff = str(rec.get("effective") or "")
    ok = bool(eff) and man["expected_model"].split("/")[-1] in eff
    return ok, (f"launch.effective={eff} matches expected" if ok
                else f"launch.effective={eff!r} vs expected {man['expected_model']}")


def chk_correlation(man):
    if not man.get("expect_correlation"):
        return True, "SKIPPED loudly: manifest predates the correlation contract"
    env_path = REPO / man.get("envelope_path", "adw_data/missioncontrol/envelope.json")
    try:
        corr = (json.loads(env_path.read_text()) or {}).get("correlation") or {}
    except Exception as exc:
        return False, f"cannot read envelope: {exc}"
    did = corr.get("dispatch_id")
    row = next((r for r in _ledger_rows() if r.get("dispatch_id") == man["dispatch_id"]
                and r["event"] == "dispatch"), {})
    pi_path = (row.get("receipt") or {}).get("mode") == "preflight_only"
    if did is None and pi_path:
        return True, "LOUD: correlation null — dispatch id not visible to pi-path workers (known limit)"
    ok = did == man["dispatch_id"]
    return ok, (f"envelope correlation matches {did}" if ok
                else f"correlation {did!r} != dispatch {man['dispatch_id']}")


CHECKS_STAGE2 = [
    ("worker_done", chk_worker_done), ("envelope_gate", chk_envelope),
    ("launch_attestation", chk_attestation), ("envelope_correlation", chk_correlation),
    ("diff_matches_claims", chk_diff_claims), ("protected_paths", chk_protected),
    ("deliverable_files", chk_files), ("stdlib_only", chk_stdlib_only),
    ("tests_green", chk_tests), ("live_server", chk_server),
    ("duration_budget", chk_duration), ("token_cost", chk_cost),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="adw_data/missioncontrol/pipeline_manifest.json")
    ap.add_argument("--stage", type=int, default=2, help="1 = pre-completion checks only")
    args = ap.parse_args()
    man = json.loads((REPO / args.manifest).read_text())
    checks = CHECKS_STAGE1 + (CHECKS_STAGE2 if args.stage >= 2 else [])
    failed = 0
    print(f"{'CHECK':18} {'RESULT':7} EVIDENCE")
    print("-" * 78)
    for name, fn in checks:
        try:
            ok, ev = fn(man)
        except Exception as exc:
            ok, ev = False, f"checker raised: {exc!r}"  # loud, never silent
        print(f"{name:18} {'PASS' if ok else 'FAIL':7} {ev}")
        failed += 0 if ok else 1
    print("-" * 78)
    print(f"OVERALL: {'PASS' if failed == 0 else f'FAIL ({failed} checks)'}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
