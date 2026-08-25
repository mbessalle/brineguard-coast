#!/usr/bin/env python3
"""Template-table Orca dispatch wrapper for SSSF supervised worker loop.

Style mirrors tools/probe.py: backend rows are data, adding a route or
changing a model is a one-line edit, not new code.

Agent rows:
  claude           orchestration worker-start --task <id> --worktree current --agent claude
  pi-openrouter    two-step: terminal create (or --terminal reuse) + dispatch --inject
  pi-openai-codex  same two-step, provider openai-codex (OAuth, no key)

Subcommands:
  run    --spec <text|@file> --route <route> [--wait] [--terminal <handle>] [--dry-run]
  wait   [--timeout <s>]                block on worker_done/escalation/question, ack
  status task-list + worker summary
  send   --dispatch <id> --body <text>  follow-up to a dispatched worker

Every live dispatch appends a JSON line to adw_data/dispatch_ledger.jsonl
(task_id, terminal, dispatch_id, route, spec head) so correlation survives
orchestrator crashes and compaction.

Grammar verified against `orca skills get orchestration` (v1.4.188+):
  check --wait --types worker_done,escalation,question --timeout-ms <n>
  a Delivery replays until `check --ack <delivery_id>`; ack after processing.
  send --to dispatch:<id> --subject <s> --body <b>
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "sssf.config.yaml"
LEDGER_PATH = REPO_ROOT / "adw_data" / "dispatch_ledger.jsonl"

WAIT_TYPES = "worker_done,escalation,question"
CHECK_CHUNK_MS = 300_000  # single rolling check --wait window (5 min)
DEFAULT_ORCA_TIMEOUT = 120  # client-side subprocess timeout for non-wait calls


def load_sssf_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def _resolve_spec(spec: str) -> str:
    """If spec starts with @, read from the named file (resolved against cwd,
    then REPO_ROOT); otherwise literal."""
    if spec.startswith("@"):
        p = Path(spec[1:])
        if not p.is_file() and not p.is_absolute():
            p = REPO_ROOT / spec[1:]
        if not p.is_file():
            sys.exit(f"spec file not found: {spec[1:]} (tried cwd and repo root)")
        return p.read_text()
    return spec


def _orca(argv: list[str], *, dry_run: bool, json_output: bool = False,
          timeout: int = DEFAULT_ORCA_TIMEOUT) -> dict | None:
    """Run an orca command with a client-side timeout. Returns the parsed
    --json payload (transport info under _rc/_stderr on trouble), or a
    {"_ok": bool} marker in plain mode. --dry-run prints and returns None.
    """
    cmd = ["orca"] + argv
    if json_output:
        cmd.append("--json")
    display_cmd = list(cmd)
    if not json_output:
        display_cmd.append("--json")

    if dry_run:
        print(f"[dry-run] would execute: {shlex.join(display_cmd)}")
        return None

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "client_timeout",
                                       "message": f"orca did not return within {timeout}s"}}
    if json_output:
        try:
            out = json.loads(proc.stdout) if proc.stdout.strip() else {}
        except json.JSONDecodeError:
            out = {"ok": False, "error": {"code": "bad_json", "message": "unparseable stdout"}}
            out["_raw"] = proc.stdout
        if proc.returncode != 0:
            out.setdefault("ok", False)
            out["_rc"] = proc.returncode
        if proc.stderr:
            out["_stderr"] = proc.stderr[-2000:]
        return out
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return {"_ok": proc.returncode == 0}


def _check_ok(result: dict | None, step: str) -> None:
    if result is None:
        return  # dry-run
    if not result.get("ok"):
        err = result.get("error") or result.get("message") or json.dumps(result)
        sys.exit(f"orca error at step '{step}': {err}")


def _ledger(record: dict) -> None:
    """Append one correlation record; never let ledger failure kill a dispatch."""
    try:
        LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with LEDGER_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        print(f"[ledger] WARNING: could not write {LEDGER_PATH}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Pi launch command
# ---------------------------------------------------------------------------

def _pi_launch_cmd(model: str, role_prompt_path: str, provider: str = "openrouter") -> str:
    """Compose the pi launch command for ``orca terminal create --command``.

    Nested inline quoting through terminal-create -> bash -> python proved
    fragile (two live failures), so the launch is written to a small script
    file and the terminal simply runs ``bash <script>``. For the openrouter
    provider the key is exported inside the script via
    tools/openrouter_call.py:load_key and never appears on argv; the
    openai-codex provider needs no key (OAuth in ~/.pi/agent/auth.json).
    The script validates the key, is strict-mode, and deletes itself.
    """
    import tempfile
    key_export = (
        "OPENROUTER_API_KEY=\"$(python3 - <<'PYEOF'\n"
        "import sys\n"
        "sys.path.insert(0, 'tools')\n"
        "from openrouter_call import load_key\n"
        "print(load_key())\n"
        "PYEOF\n"
        ")\"\n"
        "[ -n \"$OPENROUTER_API_KEY\" ] || { echo 'FATAL: empty OpenRouter key' >&2; exit 1; }\n"
        "export OPENROUTER_API_KEY\n"
    ) if provider == "openrouter" else ""
    pi_argv = ["pi", "--provider", provider, "--model", model]
    if role_prompt_path:
        pi_argv += ["--append-system-prompt", role_prompt_path]
    script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"cd {shlex.quote(str(REPO_ROOT))}\n"
        f"{key_export}"
        "rm -f -- \"$0\"\n"          # self-clean; bash keeps the open fd
        f"exec {shlex.join(pi_argv)}\n"
    )
    fd, path = tempfile.mkstemp(prefix="orca_dispatch_launch_", suffix=".sh")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(script)
    return f"bash {shlex.quote(path)}"


# ---------------------------------------------------------------------------
# Agent table  (style: tools/probe.py)
# ---------------------------------------------------------------------------
AGENTS: dict[str, dict] = {
    "claude": {
        "description": "Claude Code worker via orchestration worker-start",
        "worker_start": True,
    },
    "pi-openrouter": {
        "description": "pi with OpenRouter (two-step: terminal create + dispatch --inject)",
        "two_step": True,
        "pi_provider": "openrouter",
    },
    "pi-openai-codex": {
        "description": "pi on the OpenAI ChatGPT subscription OAuth (two-step, provider openai-codex)",
        "two_step": True,
        "pi_provider": "openai-codex",
    },
}

BACKEND_TO_AGENT = {
    "claude-cli": "claude",
    "pi-openrouter": "pi-openrouter",
    "pi-openai-codex": "pi-openai-codex",
}


# ---------------------------------------------------------------------------
# Completion wait (the previously-missing half of the handoff)
# ---------------------------------------------------------------------------

def _extract_delivery(result: dict) -> tuple[str | None, list[dict]]:
    """Defensively pull (delivery_id, messages) out of a check --json payload.
    Field names tolerated: result.delivery{.id,.messages} or flat variants."""
    res = result.get("result") or {}
    delivery = res.get("delivery") or res
    delivery_id = (delivery.get("id") or delivery.get("deliveryId")
                   or delivery.get("delivery_id"))
    messages = delivery.get("messages") or res.get("messages") or []
    if not isinstance(messages, list):
        messages = []
    return delivery_id, messages


def wait_for_completion(timeout_s: int, *, dry_run: bool = False) -> int:
    """Rolling `check --wait` until worker_done (0) or escalation (2).
    Timeout returns 3; unparseable Delivery returns 4 WITHOUT acking so the
    batch replays for manual handling. question messages are printed with
    their reply command and acked (they do not end the wait).
    An existing waiter (waiter_exists) degrades to plain-check polling."""
    if dry_run:
        print(f"[dry-run] would execute: orca orchestration check --wait "
              f"--types {WAIT_TYPES} --timeout-ms {CHECK_CHUNK_MS} --json (rolling, ack after each batch)")
        return 0
    deadline = time.monotonic() + timeout_s
    ack_id: str | None = None
    poll_mode = False
    outcome: int | None = None
    while time.monotonic() < deadline:
        argv = ["orchestration", "check", "--types", WAIT_TYPES]
        if ack_id:
            argv += ["--ack", ack_id]
        if not poll_mode:
            remaining_ms = max(10_000, min(CHECK_CHUNK_MS,
                                           int((deadline - time.monotonic()) * 1000)))
            argv += ["--wait", "--timeout-ms", str(remaining_ms)]
            client_timeout = remaining_ms // 1000 + 30
        else:
            client_timeout = DEFAULT_ORCA_TIMEOUT
        r = _orca(argv, dry_run=False, json_output=True, timeout=client_timeout)
        ack_id = None
        if not r.get("ok"):
            err_text = json.dumps(r.get("error") or r).lower()
            if "waiter" in err_text and not poll_mode:
                print("[wait] active waiter already exists; degrading to 10s polling")
                poll_mode = True
                continue
            print(f"[wait] check error: {r.get('error') or r}", file=sys.stderr)
            return 4
        delivery_id, messages = _extract_delivery(r)
        if not messages:
            if poll_mode:
                time.sleep(10)
            continue  # checkpoint ({count:0} / empty), keep waiting
        if delivery_id is None:
            print("[wait] UNPARSEABLE delivery (not acked, will replay):")
            print(json.dumps(r, indent=2)[:4000])
            return 4
        for m in messages:
            mtype = m.get("type", "?")
            mid = m.get("id", "?")
            body = m.get("body") or m.get("subject") or ""
            print(f"[wait] {mtype} id={mid}: {str(body)[:2000]}")
            if mtype == "worker_done":
                outcome = 0
            elif mtype == "escalation":
                outcome = 2
            elif mtype == "question":
                print(f"[wait]   reply with: orca orchestration reply --id {mid} "
                      f"--body '<answer>' --json")
        ack_id = delivery_id
        if outcome is not None:
            # final ack for the batch that carried the terminal message
            _orca(["orchestration", "check", "--ack", ack_id, "--types", WAIT_TYPES],
                  dry_run=False, json_output=True)
            return outcome
    print(f"[wait] timeout after {timeout_s}s — checkpoint, not failure; "
          f"worker may still be running (re-run `wait`)")
    return 3


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------

def _task_create(spec: str, *, dry_run: bool) -> str:
    """task-create with run-create fallback ONLY on a run-binding error."""
    tr = _orca(["orchestration", "task-create", "--spec", spec],
               dry_run=dry_run, json_output=not dry_run)
    if dry_run:
        return "<task_id>"
    if tr and not tr.get("ok"):
        err_text = json.dumps(tr.get("error") or tr).lower()
        if "run" in err_text and any(w in err_text for w in ("bound", "bind", "no active", "missing")):
            print("[run] no bound Run — creating one")
            rr = _orca(["orchestration", "run-create", "--objective", spec[:200]],
                       dry_run=False, json_output=True)
            _check_ok(rr, "run-create")
            tr = _orca(["orchestration", "task-create", "--spec", spec],
                       dry_run=False, json_output=True)
        # any other error class falls through to _check_ok and exits loudly
    _check_ok(tr, "task-create")
    return tr["result"]["task"]["id"]


def cmd_run(args: argparse.Namespace) -> int:
    config = load_sssf_config()
    route_name = args.route
    if route_name not in config["routes"]:
        sys.exit(f"unknown route '{route_name}'; known: {sorted(config['routes'])}")

    route = config["routes"][route_name]
    backend_name = route["backend"]
    model = route["model"]

    cost_parts = [f"{f}={route[f]}" for f in ("usd_per_m_in", "usd_per_m_out") if f in route]
    print(f"[cost] route={route_name} backend={backend_name} model={model} "
          f"{', '.join(cost_parts) if cost_parts else '(no cost data)'}")

    if backend_name not in BACKEND_TO_AGENT:
        sys.exit(f"route '{route_name}' uses backend '{backend_name}' which has no Orca "
                 f"agent mapping. Supported: {sorted(BACKEND_TO_AGENT)}. "
                 f"(session/openrouter-api routes are not dispatchable workers.)")
    agent = AGENTS[BACKEND_TO_AGENT[backend_name]]

    spec = _resolve_spec(args.spec)
    title = spec.strip().split("\n", 1)[0][:80]

    task_id = _task_create(spec, dry_run=args.dry_run)
    if not args.dry_run:
        print(f"[run] task_id={task_id}")

    term_handle = None
    dispatch_id = None

    if agent.get("worker_start"):
        ws = ["orchestration", "worker-start", "--task", task_id,
              "--worktree", "current", "--agent", "claude"]
        if model and model != "claude-fable-5":
            ws += ["--model", model]
        r = _orca(ws, dry_run=args.dry_run, json_output=not args.dry_run)
        if not args.dry_run:
            _check_ok(r, "worker-start")
            res = r.get("result") or {}
            dispatch_id = (res.get("dispatch") or {}).get("id") or res.get("dispatchId")
            print(f"[run] worker started; dispatch_id={dispatch_id}")
    else:
        # --- two-step pi path ---
        if args.terminal:
            term_handle = args.terminal
            print(f"[run] reusing terminal {term_handle} (skipping create + idle wait)")
        else:
            pi_cmd = _pi_launch_cmd(model, route.get("role_prompt", ""),
                                    provider=agent["pi_provider"])
            tc = _orca(["terminal", "create", "--worktree", "active",
                        "--title", title, "--command", pi_cmd],
                       dry_run=args.dry_run, json_output=not args.dry_run)
            if args.dry_run:
                term_handle = "<term_handle>"
            else:
                _check_ok(tc, "terminal create")
                term_handle = tc["result"]["terminal"]["handle"]
                print(f"[run] terminal handle={term_handle}")
            tw = _orca(["terminal", "wait", "--terminal", term_handle,
                        "--for", "tui-idle", "--timeout-ms", "60000"],
                       dry_run=args.dry_run, json_output=not args.dry_run,
                       timeout=90)
            if not args.dry_run:
                _check_ok(tw, "terminal wait")
        dr = _orca(["orchestration", "dispatch", "--task", task_id,
                    "--to", term_handle, "--inject"],
                   dry_run=args.dry_run, json_output=not args.dry_run)
        if not args.dry_run:
            _check_ok(dr, "orchestration dispatch")
            dispatch_id = dr["result"]["dispatch"]["id"]
            print(f"[run] dispatch_id={dispatch_id}")

    if not args.dry_run:
        _ledger({"event": "dispatch", "route": route_name, "model": model,
                 "task_id": task_id, "terminal": term_handle,
                 "dispatch_id": dispatch_id, "spec_head": title})

    if args.wait:
        rc = wait_for_completion(args.timeout, dry_run=args.dry_run)
        if not args.dry_run:
            _ledger({"event": "wait_result", "task_id": task_id,
                     "dispatch_id": dispatch_id, "rc": rc})
        return rc
    return 0


def cmd_wait(args: argparse.Namespace) -> int:
    return wait_for_completion(args.timeout, dry_run=args.dry_run)


def cmd_status(args: argparse.Namespace) -> int:
    print("=== orca orchestration task-list --brief ===")
    result = _orca(["orchestration", "task-list", "--brief"],
                   dry_run=args.dry_run, json_output=not args.dry_run)
    if args.dry_run:
        return 0
    tasks = (result.get("result") or {}).get("tasks") if isinstance(result, dict) else None
    if tasks is None and isinstance(result, list):
        tasks = result
    if tasks:
        for task in tasks:
            tid = task.get("id", "?")
            status = task.get("status", "?")
            title = task.get("title") or task.get("subject") or task.get("spec", "?")[:60]
            print(f"  {tid:20} {status:12} {title}")
    else:
        print(f"  (no tasks or unrecognized shape): {json.dumps(result)[:500]}")

    print("\n=== worker summary ===")
    _orca(["worker", "summary"], dry_run=False)
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    r = _orca(["orchestration", "send", "--to", f"dispatch:{args.dispatch}",
               "--subject", "Follow-up", "--body", args.body],
              dry_run=args.dry_run, json_output=not args.dry_run)
    if not args.dry_run:
        _check_ok(r, "send")
        print(f"[send] delivered to dispatch:{args.dispatch}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="orca_dispatch.py",
        description="Template-table Orca dispatch wrapper for SSSF supervised workers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Dispatch a spec to a route's agent.")
    p_run.add_argument("--spec", required=True, help="Prompt text, or @path/to/file.")
    p_run.add_argument("--route", required=True, help="Route name from sssf.config.yaml.")
    p_run.add_argument("--wait", action="store_true", help="Block on worker_done/escalation, ack, return.")
    p_run.add_argument("--timeout", type=int, default=3600, help="--wait budget in seconds (default 3600).")
    p_run.add_argument("--terminal", help="Reuse an existing idle pi terminal handle (skips create + 60s idle wait).")
    p_run.add_argument("--dry-run", action="store_true")

    p_wait = sub.add_parser("wait", help="Block on the Run's worker_done/escalation/question events.")
    p_wait.add_argument("--timeout", type=int, default=3600)
    p_wait.add_argument("--dry-run", action="store_true")

    p_status = sub.add_parser("status", help="Show task list + worker summary.")
    p_status.add_argument("--dry-run", action="store_true")

    p_send = sub.add_parser("send", help="Send a follow-up to a dispatched worker.")
    p_send.add_argument("--dispatch", required=True)
    p_send.add_argument("--body", required=True)
    p_send.add_argument("--dry-run", action="store_true")

    args = parser.parse_args()
    return {"run": cmd_run, "wait": cmd_wait,
            "status": cmd_status, "send": cmd_send}[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
