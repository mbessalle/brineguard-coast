#!/usr/bin/env python3
"""Template-table Orca dispatch wrapper for SSSF supervised worker loop.

Style mirrors tools/probe.py: backend rows are data, adding a route or
changing a model is a one-line edit, not new code.

Agent rows:
  claude         worker-start --agent claude
  codex          worker-start --agent codex
  pi-openrouter  two-step: terminal create + orchestration dispatch --inject

Subcommands:
  run    --spec <text|@file> --route <route-from-sssf-config> [--wait] [--dry-run]
  status task-list --brief + worker summary
  send   --dispatch <id> --body <text>

Usage:
  python3 tools/orca_dispatch.py run --spec "add X" --route builder --dry-run
  python3 tools/orca_dispatch.py status
  python3 tools/orca_dispatch.py send --dispatch ctx_abc123 --body "proceed"
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "sssf.config.yaml"


def load_sssf_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def _resolve_spec(spec: str) -> str:
    """If spec starts with @, read from the named file; otherwise literal."""
    if spec.startswith("@"):
        p = Path(spec[1:])
        if not p.is_file():
            sys.exit(f"spec file not found: {p}")
        return p.read_text()
    return spec


def _orca(argv: list[str], *, dry_run: bool, json_output: bool = False) -> dict | None:
    """Run an orca command, optionally parsing --json output. In --dry-run
    mode prints the exact command and returns None.

    --json is placed as a TRAILING flag (after the subcommand args), per the
    Orca v1.4.188 reference.
    """
    cmd = ["orca"] + argv
    if json_output:
        cmd.append("--json")
    # Build the display command — always include --json when json_output
    # would be True in live mode, so --dry-run output matches reality.
    display_cmd = list(cmd)
    if not json_output:
        display_cmd.append("--json")

    if dry_run:
        print(f"[dry-run] would execute: {' '.join(_shell_quote(c) for c in display_cmd)}")
        return None

    proc = subprocess.run(cmd, capture_output=True, text=True)
    if json_output:
        try:
            return json.loads(proc.stdout) if proc.stdout else {}
        except json.JSONDecodeError:
            return {"_raw": proc.stdout, "_stderr": proc.stderr}
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return {"_ok": proc.returncode == 0}


def _check_ok(result: dict | None, step: str) -> None:
    """Verify the top-level ``ok`` field is true; exit with a clear message
    if it is not."""
    if result is None:
        return  # dry-run, nothing to check
    if not result.get("ok"):
        err = result.get("error") or result.get("message") or json.dumps(result)
        sys.exit(f"orca error at step '{step}': {err}")


def _shell_quote(s: str) -> str:
    if not s or any(c in s for c in " \t\n\"'$"):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


# ---------------------------------------------------------------------------
# Pi-OpenRouter launch command
# ---------------------------------------------------------------------------

def _pi_openrouter_cmd(model: str, role_prompt_path: str) -> str:
    """Compose the pi launch command for ``orca terminal create --command``.

    Nested inline quoting through terminal-create -> bash -> python proved
    fragile (two live failures), so the launch is written to a small script
    file and the terminal simply runs ``bash <script>``. The key is exported
    inside the script via tools/openrouter_call.py:load_key and never appears
    on argv or in this process's output.
    """
    import tempfile
    script = (
        "#!/usr/bin/env bash\n"
        f"cd {REPO_ROOT} || exit 1\n"
        "export OPENROUTER_API_KEY=\"$(python3 - <<'PYEOF'\n"
        "import sys\n"
        "sys.path.insert(0, 'tools')\n"
        "from openrouter_call import load_key\n"
        "print(load_key())\n"
        "PYEOF\n"
        ")\"\n"
        f"exec pi --provider openrouter --model {model} --append-system-prompt {role_prompt_path}\n"
    )
    fd, path = tempfile.mkstemp(prefix="orca_dispatch_launch_", suffix=".sh")
    with open(fd, "w", encoding="utf-8") as f:
        f.write(script)
    return f"bash {path}"


# ---------------------------------------------------------------------------
# Agent table  (style: tools/probe.py)
# ---------------------------------------------------------------------------
AGENTS: dict[str, dict] = {
    "claude": {
        "description": "Claude Code agent via orca worker-start",
        "dispatch_cmd": ["worker-start", "--agent", "claude"],
    },
    "codex": {
        "description": "Codex agent via orca worker-start",
        "dispatch_cmd": ["worker-start", "--agent", "codex"],
    },
    "pi-openrouter": {
        "description": "pi with OpenRouter (two-step: terminal create + orchestration dispatch --inject)",
        "two_step": True,
    },
}


def cmd_run(args: argparse.Namespace) -> int:
    """Run a dispatch: resolve route from sssf.config.yaml, pick the right
    agent, build the orca command, and execute (or dry-run it)."""
    config = load_sssf_config()
    route_name = args.route
    if route_name not in config["routes"]:
        sys.exit(f"unknown route '{route_name}'; known: {sorted(config['routes'])}")

    route = config["routes"][route_name]
    backend_name = route["backend"]
    model = route["model"]

    # Print cost info if present
    cost_parts = []
    for field in ("usd_per_m_in", "usd_per_m_out"):
        if field in route:
            cost_parts.append(f"{field}={route[field]}")
    if cost_parts:
        print(f"[cost] route={route_name} backend={backend_name} model={model} {', '.join(cost_parts)}")
    else:
        print(f"[cost] route={route_name} backend={backend_name} model={model} (no cost data)")

    spec = _resolve_spec(args.spec)
    # Derive a short title for the terminal from the spec (first line or truncated)
    title = spec.strip().split("\n", 1)[0][:80]

    # Map backend to agent row
    if backend_name == "claude-cli":
        agent_name = "claude"
    elif backend_name == "codex-cli":
        agent_name = "codex"
    elif backend_name == "pi-openrouter":
        agent_name = "pi-openrouter"
    else:
        sys.exit(
            f"route '{route_name}' uses backend '{backend_name}' which has no "
            f"Orca agent mapping. Supported backends: claude-cli, codex-cli, pi-openrouter."
        )

    agent = AGENTS[agent_name]

    if agent.get("two_step"):
        # --- pi-openrouter path ---
        role_prompt_path = route.get("role_prompt", "")

        # Step 0 — Idempotent run-create: try task-create first; only
        # run-create if it fails for lack of a bound Run.
        print("[pi-openrouter] step 0: ensure Run exists (idempotent)")
        tr = _orca(
            ["orchestration", "task-create", "--spec", spec],
            dry_run=args.dry_run,
            json_output=not args.dry_run,
        )
        if not args.dry_run and tr and not tr.get("ok"):
            print("[pi-openrouter]   no bound Run — creating one")
            rr = _orca(
                ["orchestration", "run-create", "--objective", spec],
                dry_run=False,
                json_output=True,
            )
            _check_ok(rr, "run-create")
            tr = _orca(
                ["orchestration", "task-create", "--spec", spec],
                dry_run=False,
                json_output=True,
            )
        _check_ok(tr, "task-create")
        if args.dry_run:
            task_id = "<task_id>"
        else:
            task_id = tr["result"]["task"]["id"]
            print(f"[pi-openrouter]   task_id={task_id}")

        # Step 1 — terminal create
        pi_cmd = _pi_openrouter_cmd(model, role_prompt_path)
        print(f"[pi-openrouter] step 1: terminal create")
        tc = _orca(
            [
                "terminal", "create",
                "--worktree", "active",
                "--title", title,
                "--command", pi_cmd,
            ],
            dry_run=args.dry_run,
            json_output=not args.dry_run,
        )
        if args.dry_run:
            term_handle = "<term_handle>"
        else:
            _check_ok(tc, "terminal create")
            term_handle = tc["result"]["terminal"]["handle"]
            print(f"[pi-openrouter]   terminal handle={term_handle}")

        # Step 2 — wait for terminal to be idle
        print(f"[pi-openrouter] step 2: waiting for terminal (timeout 60s)")
        tw = _orca(
            [
                "terminal", "wait",
                "--terminal", term_handle,
                "--for", "tui-idle",
                "--timeout-ms", "60000",
            ],
            dry_run=args.dry_run,
            json_output=not args.dry_run,
        )
        if not args.dry_run:
            _check_ok(tw, "terminal wait")

        # Step 3 — orchestration dispatch --inject
        print(f"[pi-openrouter] step 3: orchestration dispatch --inject")
        dr = _orca(
            [
                "orchestration", "dispatch",
                "--task", task_id,
                "--to", term_handle,
                "--inject",
            ],
            dry_run=args.dry_run,
            json_output=not args.dry_run,
        )
        if args.dry_run:
            return 0
        _check_ok(dr, "orchestration dispatch")
        dispatch_id = dr["result"]["dispatch"]["id"]
        print(f"[pi-openrouter]   dispatch_id={dispatch_id}")

        if args.wait:
            print("[pi-openrouter] --wait requested; would block on worker_done (not implemented)")

    else:
        # Direct worker-start
        dispatch_cmd = list(agent["dispatch_cmd"])
        # For codex, spec is just the prompt; for claude, we use --spec
        if agent_name == "codex":
            dispatch_cmd.append(spec)
        else:
            dispatch_cmd.extend(["--model", model])
            dispatch_cmd.append(spec)

        result = _orca(dispatch_cmd, dry_run=args.dry_run, json_output=True)

        if args.dry_run:
            if args.wait:
                print("[dry-run] would wait for worker completion")
            return 0

        if result and args.wait:
            print("[--wait] worker dispatched; wait logic not implemented (use orca directly)")

    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Show task list + worker summary."""
    print("=== orca orchestration task-list --brief ===")
    result = _orca(
        ["orchestration", "task-list", "--brief"],
        dry_run=args.dry_run,
        json_output=not args.dry_run,
    )
    if args.dry_run:
        return 0

    if result and isinstance(result, list):
        for task in result:
            tid = task.get("id", "?")
            status = task.get("status", "?")
            title = task.get("title") or task.get("subject", "?")
            print(f"  {tid:20} {status:12} {title}")
    elif result:
        print(f"  (raw output): {result}")

    print("\n=== worker summary ===")
    _orca(["worker", "summary"], dry_run=False)
    return 0


def cmd_send(args: argparse.Namespace) -> int:
    """Send a message to a dispatched worker."""
    _orca(
        ["orchestration", "send", "--dispatch", args.dispatch, "--body", args.body],
        dry_run=args.dry_run,
        json_output=not args.dry_run,
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="orca_dispatch.py",
        description="Template-table Orca dispatch wrapper for SSSF supervised workers.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Dispatch a spec to a route's agent.")
    p_run.add_argument("--spec", required=True, help="Prompt text, or @path/to/file to read from a file.")
    p_run.add_argument("--route", required=True, help="Route name from sssf.config.yaml (e.g. builder, scout).")
    p_run.add_argument("--wait", action="store_true", help="Block until the worker completes.")
    p_run.add_argument("--dry-run", action="store_true", help="Print orca commands without executing.")

    p_status = sub.add_parser("status", help="Show task list + worker summary.")
    p_status.add_argument("--dry-run", action="store_true", help="Print orca commands without executing.")

    p_send = sub.add_parser("send", help="Send a message to a dispatched worker.")
    p_send.add_argument("--dispatch", required=True, help="Dispatch ID to target.")
    p_send.add_argument("--body", required=True, help="Message body text.")
    p_send.add_argument("--dry-run", action="store_true", help="Print orca commands without executing.")

    args = parser.parse_args()

    if args.command == "run":
        return cmd_run(args)
    elif args.command == "status":
        return cmd_status(args)
    elif args.command == "send":
        return cmd_send(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())