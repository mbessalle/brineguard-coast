#!/usr/bin/env python3
"""Generate the Factory Floor page: live Orca orchestration state as a DAG.

Reads `orca orchestration task-list`, `orca terminal list`, git, and
sssf.config.yaml; writes one self-contained HTML page (mermaid DAG + status
board) for publishing as an Artifact. Refresh = rerun + republish.

Usage: python3 tools/dag_view.py [-o out.html]
"""
from __future__ import annotations

import argparse
import datetime
import html
import json
import subprocess
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent

STATUS_CLASS = {"completed": "done", "dispatched": "active", "failed": "failed",
                "blocked": "failed", "pending": "pending", "ready": "pending"}


def orca_json(args: list[str]) -> dict | None:
    try:
        out = subprocess.run(["orca"] + args + ["--json"], capture_output=True,
                             text=True, timeout=15).stdout
        data = json.loads(out)
        return data.get("result") if data.get("ok") else None
    except Exception:
        return None


def git(*args: str) -> str:
    return subprocess.run(["git"] + list(args), cwd=REPO_ROOT, capture_output=True,
                          text=True).stdout.strip()


def build(out_path: Path) -> None:
    config = yaml.safe_load((REPO_ROOT / "sssf.config.yaml").read_text())
    tasks = (orca_json(["orchestration", "task-list"]) or {}).get("tasks", [])
    terminals = (orca_json(["terminal", "list"]) or {}).get("terminals", [])
    workers = [t for t in terminals if REPO_ROOT.name in t.get("worktreePath", "")
               or not t.get("worktreePath")]
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    commits = git("log", "--oneline", "-6").splitlines()
    branch = git("rev-parse", "--abbrev-ref", "HEAD")

    counts = {"done": 0, "active": 0, "failed": 0, "pending": 0}
    lines = ["flowchart LR"]
    for t in tasks:
        cls = STATUS_CLASS.get(t.get("status", "pending"), "pending")
        counts[cls] += 1
        label = " ".join(t.get("spec", "").split())[:46].replace('"', "'")
        tid = t["id"].replace("task_", "T")
        lines.append(f'  {tid}["{tid}<br/>{label}…"]:::{cls}')
        deps = t.get("deps") or []
        if isinstance(deps, str):
            try:
                deps = json.loads(deps)
            except ValueError:
                deps = []
        for dep in deps:
            lines.append(f'  {str(dep).replace("task_", "T")} --> {tid}')
    if not tasks:
        lines.append('  idle["No orchestration tasks in the bound run"]:::pending')
    lines += [
        "  classDef done fill:#4C9F70,stroke:#3B7A56,color:#FFFFFF",
        "  classDef active fill:#D9A441,stroke:#A87C2E,color:#1C2420",
        "  classDef failed fill:#C4554D,stroke:#93403A,color:#FFFFFF",
        "  classDef pending fill:#7A8580,stroke:#5D6662,color:#FFFFFF",
    ]
    mermaid = "\n".join(lines)

    def esc(s: str) -> str:
        return html.escape(str(s))

    worker_rows = "".join(
        f"<tr><td class='mono'>{esc(w['handle'][:17])}</td><td>{esc(w['title'][:44])}</td>"
        f"<td>{esc(w['worktreePath'].split('/')[-1] or '(floating)')}</td></tr>"
        for w in workers)
    route_rows = "".join(
        f"<tr><td>{esc(config.get('anonymization', {}).get('aliases', {}).get(name, name))}</td>"
        f"<td class='mono'>{esc(r.get('model', ''))}</td><td>{esc(r.get('backend', ''))}</td>"
        f"<td class='mono num'>{r.get('usd_per_m_in', '—')} / {r.get('usd_per_m_out', '—')}</td></tr>"
        for name, r in config.get("routes", {}).items())
    commit_rows = "".join(f"<li class='mono'>{esc(c)}</li>" for c in commits)

    out_path.write_text(f"""<title>Factory Floor</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Sora:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#F7F8F6; --surface:#FFFFFF; --ink:#1C2420; --muted:#5D6662; --line:#DDE2DE;
  --accent:#1E8A7C; --done:#4C9F70; --active:#D9A441; --failed:#C4554D; --pending:#7A8580;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#0F1417; --surface:#171E23; --ink:#E8EDEA; --muted:#93A09A; --line:#263034; --accent:#2FB8A6;
}} }}
:root[data-theme="dark"] {{
  --bg:#0F1417; --surface:#171E23; --ink:#E8EDEA; --muted:#93A09A; --line:#263034; --accent:#2FB8A6;
}}
body {{ background:var(--bg); color:var(--ink); font-family:"IBM Plex Sans",system-ui,sans-serif;
       margin:0; padding:2rem 1.5rem 3rem; }}
.wrap {{ max-width:1080px; margin:0 auto; display:flex; flex-direction:column; gap:1.4rem; }}
h1 {{ font-family:Sora,system-ui,sans-serif; font-weight:700; font-size:1.6rem; margin:0; }}
h2 {{ font-family:Sora,system-ui,sans-serif; font-weight:600; font-size:.95rem; margin:0 0 .6rem;
     text-transform:uppercase; letter-spacing:.06em; color:var(--muted); }}
.meta {{ color:var(--muted); font-size:.85rem; }}
.strip {{ display:flex; gap:.8rem; flex-wrap:wrap; }}
.pill {{ background:var(--surface); border:1px solid var(--line); border-radius:999px;
        padding:.35rem .9rem; font-size:.85rem; display:flex; gap:.45rem; align-items:center; }}
.dot {{ width:.55rem; height:.55rem; border-radius:50%; display:inline-block; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:1.1rem 1.2rem; }}
.dag {{ overflow-x:auto; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:1.4rem; }}
@media (max-width:820px) {{ .cols {{ grid-template-columns:1fr; }} }}
table {{ border-collapse:collapse; width:100%; font-size:.83rem; }}
td, th {{ text-align:left; padding:.4rem .55rem; border-bottom:1px solid var(--line); vertical-align:top; }}
th {{ color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:.05em; font-size:.72rem; }}
.mono {{ font-family:"IBM Plex Mono",monospace; font-size:.8rem; }}
.num {{ font-variant-numeric:tabular-nums; }}
ul {{ margin:.2rem 0 0; padding-left:1.1rem; }} li {{ margin:.2rem 0; font-size:.8rem; }}
.accent {{ color:var(--accent); }}
</style>
<div class="wrap">
  <div>
    <h1>Factory Floor</h1>
    <div class="meta">BrineGuard SSSF · branch <span class="mono accent">{esc(branch)}</span> · snapshot {now} ·
    refresh: <span class="mono">python3 tools/dag_view.py</span> + republish</div>
  </div>
  <div class="strip">
    <span class="pill"><span class="dot" style="background:var(--done)"></span>{counts['done']} done</span>
    <span class="pill"><span class="dot" style="background:var(--active)"></span>{counts['active']} active</span>
    <span class="pill"><span class="dot" style="background:var(--failed)"></span>{counts['failed']} failed/blocked</span>
    <span class="pill"><span class="dot" style="background:var(--pending)"></span>{counts['pending']} pending</span>
    <span class="pill">{len(workers)} terminals live</span>
  </div>
  <div class="card dag">
    <h2>Task DAG (bound Orca run)</h2>
    <pre class="mermaid">{mermaid}</pre>
  </div>
  <div class="cols">
    <div class="card"><h2>Live terminals</h2>
      <table><tr><th>Handle</th><th>Title</th><th>Worktree</th></tr>{worker_rows}</table></div>
    <div class="card"><h2>Model routes (anonymized aliases)</h2>
      <table><tr><th>Alias</th><th>Model</th><th>Backend</th><th>$/M in·out</th></tr>{route_rows}</table></div>
  </div>
  <div class="card"><h2>Recent commits</h2><ul>{commit_rows}</ul></div>
</div>
""", encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-o", "--out", default=str(REPO_ROOT / "adw_data" / "factory_floor.html"))
    args = parser.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
