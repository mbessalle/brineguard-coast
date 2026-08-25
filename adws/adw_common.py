"""Shared plumbing for SSSF ADW runner scripts.

Not itself a workflow. Provides: config loading, session-id/dir helpers,
route-based backend execution via sssf.config.yaml, phase logging,
and envelope writing. Kept deliberately small — see adws/README.md for the
Engineer/Agent/Code separation this supports.
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "sssf.config.yaml"
SESSION_ROOT = REPO_ROOT / "adw_data" / "sessions"


def load_config() -> dict:
    with CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def model_for_role(config: dict, role: str) -> str:
    """Resolve which model backs a given role per the tiered stack.

    For Tier 2 workhorse roles the values are route names (see
    sssf.config.yaml tiers.tier_2_workhorse.models); for Tier 1 roles
    the value is the model id directly.
    """
    tier_name = config["routing"]["default_tier_by_role"][role]
    tier = config["tiers"][tier_name]
    if "model" in tier:
        return tier["model"]
    return tier["models"][role]


def route_model(config: dict, route_name: str) -> str:
    """Return the model id backing a given route."""
    return config["routes"][route_name]["model"]


def new_session_id() -> str:
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def handoff_dir(session_id: str) -> Path:
    return SESSION_ROOT / session_id / "context_handoff"


def ensure_handoff_dir(session_id: str) -> Path:
    d = handoff_dir(session_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


class PhaseLogger:
    """Logs each phase start/end + gate results to stdout and to a
    per-session log file under the handoff directory."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.dir = ensure_handoff_dir(session_id)
        self.log_path = self.dir / "run.log"

    def _write(self, line: str) -> None:
        stamped = f"[{datetime.datetime.now().isoformat(timespec='seconds')}] {line}"
        print(stamped)
        with self.log_path.open("a") as f:
            f.write(stamped + "\n")

    def phase_start(self, phase: str, role: str, model: str) -> None:
        self._write(f"PHASE START  phase={phase} role={role} model={model}")

    def phase_end(self, phase: str, ok: bool) -> None:
        status = "OK" if ok else "FAIL"
        self._write(f"PHASE END    phase={phase} status={status}")

    def gate_result(self, result: dict) -> None:
        self._write(f"GATE RESULT  {json.dumps(result, default=str)}")

    def info(self, message: str) -> None:
        self._write(f"INFO         {message}")


def run_route(
    route_name: str,
    prompt: str,
    *,
    role_prompt_override: str | None = None,
    dry_run: bool = False,
    logger: "PhaseLogger | None" = None,
) -> tuple[bool, str]:
    """Execute a route from sssf.config.yaml.

    Reads `backends` + `routes`, resolves the backend's argv template
    (substituting {model}, {prompt}, {role_prompt}), sets up env vars from
    the backend definition, and runs the subprocess.

    Backend `session` is orchestrator-only — raises ValueError unless in
    dry-run mode (where it prints a warning and returns a placeholder).
    PI-openrouter backend reads OPENROUTER_API_KEY via
    tools/openrouter_call.py:load_key (the key never appears on stdout or
    argv).
    """
    config = load_config()
    route = config["routes"][route_name]
    backend_name = route["backend"]
    backend = config["backends"][backend_name]
    model = route["model"]

    # Resolve role prompt
    rp_source = role_prompt_override if role_prompt_override is not None else route.get("role_prompt", "")
    role_prompt = ""
    if rp_source:
        rp_path = Path(rp_source)
        if rp_path.exists():
            role_prompt = rp_path.read_text()
        else:
            role_prompt = rp_source

    if backend_name == "session":
        msg = (
            f"Route '{route_name}' uses backend 'session', which is "
            f"an orchestrator-only route (Tier 1 SOTA roles like planner/"
            f"reviewer are invoked by the orchestrating session itself, not "
            f"via subprocess)."
        )
        if dry_run:
            if logger:
                logger.info(f"[dry-run] {msg}")
            print(f"[dry-run] {msg}")
            return True, "<dry-run: orchestrator-only route not invoked>"
        raise ValueError(msg)

    # Build argv by substituting {model}, {prompt}, {role_prompt}
    invoke = backend["invoke"]
    argv = [a.format(model=model, prompt=prompt, role_prompt=role_prompt) for a in invoke]

    # Build env
    env = dict(os.environ)
    if backend_name == "pi-openrouter":
        tools_dir = str(REPO_ROOT / "tools")
        if tools_dir not in sys.path:
            sys.path.insert(0, tools_dir)
        from openrouter_call import load_key  # noqa: E402
        env["OPENROUTER_API_KEY"] = load_key()

    if dry_run:
        if logger:
            logger.info(f"[dry-run] route={route_name} backend={backend_name} model={model}")
        print(f"[dry-run] would execute: {' '.join(_shell_quote(a) for a in argv)}")
        return True, "<dry-run: no LLM invoked>"

    if logger:
        logger.info(f"invoking route={route_name} backend={backend_name} model={model}")

    proc = subprocess.run(argv, cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    ok = proc.returncode == 0
    output = proc.stdout if ok else (proc.stdout + "\n" + proc.stderr)
    return ok, output


def run_claude(
    prompt: str,
    model: str,
    *,
    dry_run: bool,
    permission_mode: str = "bypassPermissions",
    cwd: Path | None = None,
) -> tuple[bool, str]:
    """Thin compatibility wrapper — invoke `claude` CLI headless.

    Preferred path is run_route() which reads backends from
    ssssf.config.yaml. Use this only when you need direct claude CLI access
    outside the route table (e.g. session-backend roles from a CLI script).
    """
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        model,
        "--output-format",
        "text",
        "--permission-mode",
        permission_mode,
    ]

    if dry_run:
        print(f"[dry-run] would execute: {' '.join(_shell_quote(c) for c in cmd)}")
        return True, "<dry-run: no LLM invoked>"

    proc = subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True)
    ok = proc.returncode == 0
    output = proc.stdout if ok else (proc.stdout + "\n" + proc.stderr)
    return ok, output


def _shell_quote(s: str) -> str:
    if not s or any(c in s for c in " \t\n\"'$"):
        return "'" + s.replace("'", "'\\''") + "'"
    return s


def write_envelope(path: Path, *, status: str, summary: str, changed_files: list[str], **extra: Any) -> None:
    payload = {"status": status, "summary": summary, "changed_files": changed_files, **extra}
    path.write_text(json.dumps(payload, indent=2))


def write_text(path: Path, text: str) -> None:
    path.write_text(text)


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)
