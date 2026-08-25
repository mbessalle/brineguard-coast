#!/usr/bin/env python3
"""Generate the Factory Floor page: live Orca orchestration state.

Reads `orca orchestration task-list`, `orca terminal list`, the dispatch
ledger, git, and sssf.config.yaml; writes one self-contained HTML page.
Refresh = rerun + republish.

Design: a status BOARD (tasks grouped by state, full wrapped text, ledger
join for route/model/cost), not a mermaid strip — our tasks are mostly
parallel, so a flowchart of disconnected boxes carried no information. A
mermaid DAG section renders only when real dependency edges exist.

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
LEDGER = REPO_ROOT / "adw_data" / "dispatch_ledger.jsonl"

STATUS_ORDER = ["active", "failed", "pending", "done"]
STATUS_OF = {"completed": "done", "dispatched": "active", "failed": "failed",
             "blocked": "failed", "pending": "pending", "ready": "pending"}
STATUS_LABEL = {"active": "Active", "failed": "Failed / blocked",
                "pending": "Pending", "done": "Completed"}


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


def load_ledger() -> dict[str, dict]:
    """task_id -> latest dispatch row (+cost from a matching wait_result)."""
    by_task: dict[str, dict] = {}
    if not LEDGER.exists():
        return by_task
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        tid = r.get("task_id")
        if not tid:
            continue
        if r.get("event") == "dispatch":
            by_task[tid] = r
        elif r.get("event") == "wait_result" and tid in by_task:
            by_task[tid]["rc"] = r.get("rc")
            if "cost_usd_delta" in r:
                by_task[tid]["cost_usd_delta"] = r["cost_usd_delta"]
    return by_task


def build(out_path: Path) -> None:
    config = yaml.safe_load((REPO_ROOT / "sssf.config.yaml").read_text())
    tasks = (orca_json(["orchestration", "task-list"]) or {}).get("tasks", [])
    terminals = (orca_json(["terminal", "list"]) or {}).get("terminals", [])
    ledger = load_ledger()
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    now = now_dt.strftime("%Y-%m-%d %H:%M UTC")
    commits = git("log", "--oneline", "-8").splitlines()
    branch = git("rev-parse", "--abbrev-ref", "HEAD")

    def esc(s) -> str:
        return html.escape(str(s))

    def age(ts: str) -> str:
        try:
            t = datetime.datetime.fromisoformat(ts)
            mins = int((now_dt - t).total_seconds() // 60)
            return f"{mins // 60}h {mins % 60:02d}m ago" if mins >= 60 else f"{mins}m ago"
        except Exception:
            return ""

    # ---- board: tasks grouped by status, newest first --------------------
    groups: dict[str, list[dict]] = {k: [] for k in STATUS_ORDER}
    for t in tasks:
        groups[STATUS_OF.get(t.get("status", "pending"), "pending")].append(t)
    counts = {k: len(v) for k, v in groups.items()}

    def task_card(t: dict) -> str:
        tid = t["id"]
        led = ledger.get(tid, {})
        spec = " ".join(t.get("spec", "").split())
        head, rest = spec[:160], spec[160:]
        meta_bits = []
        if led.get("route"):
            meta_bits.append(f"{esc(led['route'])} · <span class='mono'>{esc(led.get('model',''))}</span>")
        if led.get("terminal"):
            meta_bits.append(f"<span class='mono'>{esc(led['terminal'][:22])}</span>")
        if led.get("ts"):
            meta_bits.append(esc(age(led["ts"])))
        if "cost_usd_delta" in led:
            meta_bits.append(f"${led['cost_usd_delta']:.4f}")
        detail = (f"<details><summary>full spec</summary><p class='spec'>{esc(spec)}</p></details>"
                  if rest else "")
        return (f"<div class='task s-{STATUS_OF.get(t.get('status','pending'),'pending')}'>"
                f"<div class='tid mono'>{esc(tid)} <span class='st'>{esc(t.get('status','?'))}</span></div>"
                f"<div class='head'>{esc(head)}{'…' if rest else ''}</div>"
                f"{detail}"
                f"<div class='tmeta'>{' · '.join(meta_bits)}</div></div>")

    board = ""
    for key in STATUS_ORDER:
        if not groups[key]:
            continue
        cards = "".join(task_card(t) for t in reversed(groups[key]))
        board += (f"<section class='lane'><h2>{STATUS_LABEL[key]} "
                  f"<span class='count'>{counts[key]}</span></h2>{cards}</section>")
    if not tasks:
        board = "<section class='lane'><h2>No orchestration tasks in the bound run</h2></section>"

    # ---- optional real DAG (only when dependency edges exist) ------------
    edges = []
    for t in tasks:
        deps = t.get("deps") or []
        if isinstance(deps, str):
            try:
                deps = json.loads(deps)
            except ValueError:
                deps = []
        for dep in deps:
            edges.append((str(dep), t["id"]))
    dag_section = ""
    if edges:
        lines = ["flowchart LR"]
        for a, b in edges:
            lines.append(f'  {a.replace("task_","T")} --> {b.replace("task_","T")}')
        dag_section = (f"<div class='card dagwrap'><h2>Dependency edges</h2>"
                       f"<pre class='mermaid'>{chr(10).join(lines)}</pre></div>")

    workers = [t for t in terminals if REPO_ROOT.name in t.get("worktreePath", "")
               or not t.get("worktreePath")]
    worker_rows = "".join(
        f"<tr><td class='mono'>{esc(w['handle'].replace('term_','')[:12])}</td>"
        f"<td class='wt'>{esc(w['title'])}</td>"
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
  --lane:#EFF2EF;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg:#0F1417; --surface:#171E23; --ink:#E8EDEA; --muted:#93A09A; --line:#263034;
  --accent:#2FB8A6; --lane:#131A1E;
}} }}
:root[data-theme="dark"] {{
  --bg:#0F1417; --surface:#171E23; --ink:#E8EDEA; --muted:#93A09A; --line:#263034;
  --accent:#2FB8A6; --lane:#131A1E;
}}
* {{ box-sizing:border-box; }}
body {{ background:var(--bg); color:var(--ink); font-family:"IBM Plex Sans",system-ui,sans-serif;
       margin:0; padding:2rem 1.5rem 3rem; }}
.wrap {{ max-width:1100px; margin:0 auto; display:flex; flex-direction:column; gap:1.3rem; }}
h1 {{ font-family:Sora,system-ui,sans-serif; font-weight:700; font-size:1.6rem; margin:0; }}
h2 {{ font-family:Sora,system-ui,sans-serif; font-weight:600; font-size:.85rem; margin:0 0 .7rem;
     text-transform:uppercase; letter-spacing:.07em; color:var(--muted); }}
.count {{ color:var(--accent); }}
.meta {{ color:var(--muted); font-size:.85rem; line-height:1.5; }}
.strip {{ display:flex; gap:.7rem; flex-wrap:wrap; }}
.pill {{ background:var(--surface); border:1px solid var(--line); border-radius:999px;
        padding:.35rem .9rem; font-size:.85rem; display:flex; gap:.45rem; align-items:center;
        font-variant-numeric:tabular-nums; }}
.dot {{ width:.55rem; height:.55rem; border-radius:50%; }}
.lane {{ background:var(--lane); border:1px solid var(--line); border-radius:12px; padding:1rem 1.1rem; }}
.task {{ background:var(--surface); border:1px solid var(--line); border-left:4px solid var(--pending);
        border-radius:8px; padding:.7rem .9rem; margin:.55rem 0; }}
.task.s-done {{ border-left-color:var(--done); }}
.task.s-active {{ border-left-color:var(--active); }}
.task.s-failed {{ border-left-color:var(--failed); }}
.tid {{ font-size:.72rem; color:var(--muted); display:flex; justify-content:space-between; gap:.6rem; }}
.st {{ text-transform:uppercase; letter-spacing:.05em; }}
.head {{ font-size:.92rem; line-height:1.45; margin:.3rem 0 .15rem; overflow-wrap:anywhere; }}
.spec {{ font-size:.82rem; color:var(--muted); line-height:1.5; overflow-wrap:anywhere; margin:.4rem 0 0; }}
details summary {{ font-size:.75rem; color:var(--accent); cursor:pointer; }}
.tmeta {{ font-size:.75rem; color:var(--muted); margin-top:.35rem; overflow-wrap:anywhere;
         font-variant-numeric:tabular-nums; }}
.card {{ background:var(--surface); border:1px solid var(--line); border-radius:10px; padding:1rem 1.1rem; }}
.cols {{ display:grid; grid-template-columns:1fr 1fr; gap:1.3rem; }}
@media (max-width:860px) {{ .cols {{ grid-template-columns:1fr; }} }}
.tblwrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:.83rem; }}
td, th {{ text-align:left; padding:.45rem .55rem; border-bottom:1px solid var(--line);
         vertical-align:top; overflow-wrap:anywhere; }}
th {{ color:var(--muted); font-weight:500; text-transform:uppercase; letter-spacing:.05em; font-size:.7rem; }}
.wt {{ min-width:12rem; }}
.mono {{ font-family:"IBM Plex Mono",monospace; font-size:.78rem; }}
.num {{ font-variant-numeric:tabular-nums; white-space:nowrap; }}
ul {{ margin:.2rem 0 0; padding-left:1.1rem; }} li {{ margin:.25rem 0; font-size:.8rem; overflow-wrap:anywhere; }}
.accent {{ color:var(--accent); }}
.dagwrap {{ overflow-x:auto; }}
</style>
<div class="wrap">
  <div>
    <h1>Factory Floor</h1>
    <div class="meta">BrineGuard SSSF · branch <span class="mono accent">{esc(branch)}</span> · snapshot {now}<br>
    Refresh: <span class="mono">python3 tools/dag_view.py</span> + republish. Cards join Orca task state with the dispatch ledger (route, model, terminal, age, measured cost).</div>
  </div>
  <div class="strip">
    <span class="pill"><span class="dot" style="background:var(--active)"></span>{counts['active']} active</span>
    <span class="pill"><span class="dot" style="background:var(--failed)"></span>{counts['failed']} failed/blocked</span>
    <span class="pill"><span class="dot" style="background:var(--pending)"></span>{counts['pending']} pending</span>
    <span class="pill"><span class="dot" style="background:var(--done)"></span>{counts['done']} completed</span>
    <span class="pill">{len(workers)} terminals live</span>
  </div>
  {board}
  {dag_section}
  <div class="cols">
    <div class="card"><h2>Live terminals</h2><div class="tblwrap">
      <table><tr><th>Handle</th><th>Title</th><th>Worktree</th></tr>{worker_rows}</table></div></div>
    <div class="card"><h2>Model routes (anonymized aliases)</h2><div class="tblwrap">
      <table><tr><th>Alias</th><th>Model</th><th>Backend</th><th>$/M in·out</th></tr>{route_rows}</table></div></div>
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
