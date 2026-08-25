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


def parse_verdict(output: str) -> tuple[str, str]:
    """Extract verdict enum and reason from reviewer output.

    Returns (verdict, reason) where verdict is one of
    APPROVE|REQUEST-CHANGES|PARTIAL|BLOCKED.  reason is the rest of the
    verdict line after the enum (empty string if not found).
    Raises ValueError on unparseable output.
    """
    VALID = {"APPROVE", "REQUEST-CHANGES", "PARTIAL", "BLOCKED"}
    for line in output.splitlines():
        stripped = line.strip()
        for v in VALID:
            if stripped.startswith(v):
                reason = stripped[len(v):].lstrip(":- ").strip()
                return v, reason
    raise ValueError(f"no valid verdict line found in reviewer output ({output[:200]!r})")


def retry_ladder(
    route_name: str,
    prompt_template: str,
    *,
    plan_text: str,
    dry_run: bool,
    logger: "PhaseLogger",
    handoff: Path,
    config: dict | None = None,
) -> tuple[int, str, int]:
    """Run builder with retry ladder from sssf.config.yaml.

    On quality-gate failure, retry the SAME builder with raw stderr/stdout
    up to max_builder_retries; then escalate to builder_escalation with a
    fresh retry budget; then stop.

    Returns (exit_code, last_output, total_attempts). exit_code 0 = success.
    """
    if config is None:
        config = load_config()

    retry_policy = config["routing"]["retry_policy"]
    max_retries = retry_policy["max_builder_retries"]
    escalation_ladder = retry_policy.get("model_escalation", ["builder", "builder_escalation", "planner"])

    # Only the first two rungs are subprocess-invocable; planner is session-only.
    invocable_rungs = [r for r in escalation_ladder if r in ("builder", "builder_escalation")]
    if not invocable_rungs:
        die("no invocable rungs in model_escalation; cannot run builder")

    total_attempts = 0
    gate_result: dict = {}
    last_output = ""

    for rung in invocable_rungs:
        budget = max_retries
        for attempt in range(1, budget + 1):
            total_attempts += 1
            logger.phase_start(f"builder({rung} attempt {attempt})", "builder", rung)

            retry_context = ""
            if total_attempts > 1:
                retry_context = f"""
The previous attempt failed the deterministic quality gate. Fix ONLY what is
needed to make the gate pass; do not change the plan's scope.

--- GATE FAILURE OUTPUT (attempt {total_attempts - 1}) ---
{json.dumps(gate_result, indent=2, default=str)[:8000]}
--- END GATE FAILURE OUTPUT ---
"""
            builder_prompt = prompt_template.format(plan=plan_text, retry_context=retry_context)

            ok, builder_output = run_route(rung, builder_prompt, dry_run=dry_run, logger=logger)
            last_output = builder_output

            envelope_path = handoff / "envelope.json"
            changed_files = [] if dry_run else _git_diff_files()
            write_envelope(
                envelope_path,
                status="succeeded" if (dry_run or ok) else "failed",
                summary=f"builder {rung} attempt {attempt}",
                changed_files=changed_files,
            )

            # Validate envelope via json_parse gate
            import gates  # noqa: E402
            env_gate = gates.json_parse(str(envelope_path))
            if not env_gate["pass"]:
                logger.gate_result(env_gate)
                logger.info(f"envelope validation failed; aborting")
                return 2, last_output, total_attempts

            logger.phase_end(f"builder({rung} attempt {attempt})", dry_run or ok)

            if dry_run:
                return 0, last_output, total_attempts

            # Run deterministic quality gate
            gate_result = gates.code_quality()
            (handoff / "gate_results.json").write_text(json.dumps(gate_result, indent=2, default=str))
            (handoff / "test_log.txt").write_text(json.dumps(gate_result.get("detail", {}), indent=2, default=str))
            logger.gate_result(gate_result)

            if gate_result["pass"]:
                logger.info(f"builder succeeded on {rung} attempt {attempt}")
                return 0, last_output, total_attempts

            logger.info(f"gate failed on {rung} attempt {attempt}/{budget}")

        # Rung exhausted — escalate
        logger.info(f"{rung} exhausted {budget} retries; escalating to next rung")

    # All rungs exhausted
    logger.info("all builder rungs exhausted; escalation to planner required")
    return 1, last_output, total_attempts


def codex_compose_prompt(role_prompt_path: str, task_prompt: str) -> str:
    """Compose a prompt for the codex-cli backend.

    codex-cli has no system-prompt flag, so we prepend the role prompt
    file content before the task prompt, separated by a marker.
    """
    rp = ""
    if role_prompt_path:
        p = Path(role_prompt_path)
        if p.exists():
            rp = p.read_text()
        else:
            rp = role_prompt_path
    if rp.strip():
        return rp.strip() + "\n\n--- TASK ---\n\n" + task_prompt
    return task_prompt


def _git_diff_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line]


def _git_diff_full() -> str:
    try:
        proc = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return "(git diff unavailable)"
    if proc.returncode != 0:
        return "(git diff failed)"
    return proc.stdout or "(no changes)"


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

    Backend `codex-cli` has no --system-prompt flag; the role_prompt file
    content is prepended to the task prompt before invocation.
    """
    config = load_config()
    route = config["routes"][route_name]
    backend_name = route["backend"]
    backend = config["backends"][backend_name]
    model = route["model"]

    # Resolve role prompt source
    rp_source = role_prompt_override if role_prompt_override is not None else route.get("role_prompt", "")

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

    # codex-cli: compose role_prompt + task_prompt (no --system-prompt flag)
    if backend_name == "codex-cli":
        composed = codex_compose_prompt(rp_source, prompt)
        # Re-resolve with composed prompt in place; the invoke template has
        # {prompt} only (no {role_prompt}) so we substitute composed directly.
        role_prompt = ""
        final_prompt = composed
    else:
        role_prompt = ""
        if rp_source:
            rp_path = Path(rp_source)
            if rp_path.exists():
                role_prompt = rp_path.read_text()
            else:
                role_prompt = rp_source
        final_prompt = prompt

    # Build argv by substituting {model}, {prompt}, {role_prompt}
    invoke = backend["invoke"]
    argv = [a.format(model=model, prompt=final_prompt, role_prompt=role_prompt) for a in invoke]

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
    if status not in ("succeeded", "failed"):
        raise ValueError(f"envelope status must be 'succeeded' or 'failed', got {status!r}")
    payload = {"status": status, "summary": summary, "changed_files": changed_files, **extra}
    path.write_text(json.dumps(payload, indent=2))


def write_text(path: Path, text: str) -> None:
    path.write_text(text)


def die(message: str, code: int = 1) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(code)
