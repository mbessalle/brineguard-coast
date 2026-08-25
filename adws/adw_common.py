"""Shared plumbing for SSSF ADW runner scripts.

Not itself a workflow. Provides: config loading, session-id/dir helpers,
headless `claude` CLI invocation (Tier 1 / Tier 2 phases), phase logging,
and envelope writing. Kept deliberately small — see adws/README.md for the
Engineer/Agent/Code separation this supports.
"""

from __future__ import annotations

import datetime
import json
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
    """Resolve which model backs a given role per the tiered stack."""
    tier_name = config["routing"]["default_tier_by_role"][role]
    tier = config["tiers"][tier_name]
    if "model" in tier:
        return tier["model"]
    return tier["models"][role]


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


def run_claude(
    prompt: str,
    model: str,
    *,
    dry_run: bool,
    permission_mode: str = "bypassPermissions",
    cwd: Path | None = None,
) -> tuple[bool, str]:
    """Invoke the `claude` CLI headless (Tier 1/2 phase). Returns
    (ok, output_text). In --dry-run mode, prints the command that would run
    and returns (True, "<dry-run: no LLM invoked>") without touching the
    network or any model.
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
