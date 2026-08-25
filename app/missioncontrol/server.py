#!/usr/bin/env python3
"""BrineGuard Mission Control — stdlib-only HTTP server + repo parsers.

Run: python3 app/missioncontrol/server.py --port N

All headline/claim/run values are parsed read-only from repo files
(docs/CLAIMS.md, docs/FREEZE.md, BUILD_PLAN.md, runs/*). Nothing is invented.
"""
import argparse
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CLAIMS_PATH = REPO / "docs" / "CLAIMS.md"
FREEZE_PATH = REPO / "FREEZE.md"
BUILD_PLAN_PATH = REPO / "BUILD_PLAN.md"
RUNS_DIR = REPO / "runs"


# --------------------------------------------------------------------------
# Parsers (importable + unit-tested)
# --------------------------------------------------------------------------

def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def parse_claims(path: Path | None = None) -> list[dict]:
    """Extract canonical claim text for C1..C6 from docs/CLAIMS.md."""
    path = path or CLAIMS_PATH
    claims = []
    current_id = None
    current_lines = []

    def flush():
        nonlocal current_id, current_lines
        if current_id is None:
            return
        body = "\n".join(current_lines)
        m = re.search(
            r"\*\*Claim:\*\*\s*(.*?)(?=\n\*\*(?:Conditions|Evidence|Framing rule):\*\*)",
            body, re.DOTALL,
        )
        raw = m.group(1) if m else body  # C6 has no "Claim:" marker
        claims.append({"id": current_id, "text": _norm(raw.replace("*", ""))})
        current_id = None
        current_lines = []

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            flush()
            m = re.match(r"^## (C\d+)\b", line)
            current_id = m.group(1) if m else None
            current_lines = []
        elif current_id is not None:
            current_lines.append(line)
    flush()
    return claims


def parse_project(path: Path | None = None) -> str:
    path = path or CLAIMS_PATH
    first = path.read_text(encoding="utf-8").splitlines()[0]
    m = re.match(r"^#\s+(.+?)\s+—", first)
    return m.group(1) if m else "BrineGuard Coast"


def parse_freeze_commit(path: Path | None = None) -> str:
    path = path or FREEZE_PATH
    m = re.search(r"at git ([0-9a-f]{7,})", path.read_text(encoding="utf-8"))
    return m.group(1) if m else ""


def parse_phases(path: Path | None = None) -> list[dict]:
    path = path or BUILD_PLAN_PATH
    phases = []
    for m in re.finditer(r"\*\*Phase (\d+) — ([^(\n]+?)\s*\(", path.read_text(encoding="utf-8")):
        phases.append({"id": f"Phase {m.group(1)}", "name": _norm(m.group(2))})
    return phases


def parse_headline(repo: Path | None = None) -> dict:
    repo = repo or REPO
    comp = json.loads((repo / "runs" / "phase3-headline" / "comparison.json").read_text())

    def benefit(cell: str, strat: str) -> float:
        return comp["cells"][cell]["strategies"][strat]["coordination_benefit"]

    steady_cap = benefit("phase3/flex4", "C_matched_capacity")
    steady_cost = benefit("phase3/flex4", "C_matched_cost")
    tidal_cap = benefit("phase3_tidal/flex4", "C_matched_capacity")
    tidal_cost = benefit("phase3_tidal/flex4", "C_matched_cost")

    ens = json.loads((repo / "runs" / "phase4-ensemble-v2" / "ensemble.json").read_text())
    min_cap = min(ens["strategies"]["B_capacity"]["benefit_distribution"])
    min_cost = min(ens["strategies"]["B_cost"]["benefit_distribution"])

    def pct(x: float) -> str:
        return f"{round(x * 100, 1)}%"

    def rng(a: float, b: float) -> str:
        lo, hi = sorted(round(v * 100, 1) for v in (a, b))
        return f"{lo}–{hi}%"

    return {
        "steady": rng(steady_cap, steady_cost),
        "tidal": rng(tidal_cap, tidal_cost),
        "ensemble_min_capacity": pct(min_cap),
        "ensemble_min_cost": pct(min_cost),
    }


def parse_summary(repo: Path | None = None) -> dict:
    repo = repo or REPO
    return {
        "project": parse_project(),
        "phases": parse_phases(),
        "headline": parse_headline(repo),
        "freeze_commit": parse_freeze_commit(),
    }


def _infer_status(run_dir: Path) -> str:
    val = run_dir / "validation.json"
    if val.exists():
        data = json.loads(val.read_text())
        passes = [v for k, v in data.items() if k.endswith("_pass")]
        if passes and all(v is True for v in passes):
            return "complete"
        if passes:
            return "failed"
    for art in ("comparison.json", "ensemble.json", "sensitivity.json"):
        if (run_dir / art).exists():
            return "complete"
    return "unknown"


def parse_runs(repo: Path | None = None) -> list[dict]:
    repo = repo or REPO
    runs = []
    for run_dir in sorted((repo / "runs").iterdir()):
        if not run_dir.is_dir():
            continue
        manifest = json.loads((run_dir / "manifest.json").read_text())
        status = manifest.get("status") or _infer_status(run_dir)
        runs.append({
            "name": run_dir.name,
            "run_id": manifest.get("run_id", run_dir.name),
            "status": status,
            "created_utc": manifest.get("created_utc"),
            "git_revision": manifest.get("git_revision"),
        })
    return runs


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    data = {}  # populated at startup

    def do_GET(self):
        if self.path == "/":
            self._serve_file(REPO / "app" / "missioncontrol" / "index.html",
                             "text/html; charset=utf-8")
        elif self.path == "/api/summary":
            self._serve_json(self.data["summary"])
        elif self.path == "/api/claims":
            self._serve_json(self.data["claims"])
        elif self.path == "/api/runs":
            self._serve_json(self.data["runs"])
        else:
            self.send_error(404)

    def _serve_json(self, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self, path: Path, ctype: str):
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="BrineGuard Mission Control server")
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args(argv)
    Handler.data = {
        "summary": parse_summary(),
        "claims": parse_claims(),
        "runs": parse_runs(),
    }
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"BrineGuard Mission Control listening on http://127.0.0.1:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
