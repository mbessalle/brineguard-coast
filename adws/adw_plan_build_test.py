#!/usr/bin/env python3
"""adw_plan_build_test: Planner (SOTA) -> Builder (Workhorse) -> Test/Gate
(Code) -> git commit.

Implements the bounded-retry policy from sssf.config.yaml: on a gate
failure, the raw failure output is handed back to the Tier 2 builder for a
fix attempt (max `routing.retry_policy.max_builder_retries`, default 3).
Only after retries are exhausted does the workflow escalate to the Tier 1
planner (and it stops there — this script does not auto-replan; escalation
means "flag for a human/planner session", not "call the planner again
unbounded").

Usage:
    .venv/bin/python adws/adw_plan_build_test.py --request "add X" --dry-run
    .venv/bin/python adws/adw_plan_build_test.py --request "add X"

Output (adw_data/sessions/<session_id>/context_handoff/):
    plan.md, plan.json          (planner)
    envelope.json                (builder, last attempt)
    gate_results.json, test_log.txt  (deterministic gate)
    escalation.json              (only if retries exhausted)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adw_common  # noqa: E402
import gates  # noqa: E402

PLANNER_PROMPT_TEMPLATE = """You are the Planner in an SSSF pipeline (Tier 1, SOTA).

Feature request: {request}

Produce an implementation plan for the Tier 2 Builder to follow exactly.
Write the plan as Markdown: goal, files to touch, step-by-step changes,
and how to verify. Do not write code yourself; the Builder does that.
"""

BUILDER_PROMPT_TEMPLATE = """You are the Builder in an SSSF pipeline (Tier 2, Workhorse).

Follow this plan exactly. Make the file edits it describes.

--- PLAN ---
{plan}
--- END PLAN ---
{retry_context}
When done, summarize what changed.
"""

RETRY_CONTEXT_TEMPLATE = """
The previous attempt failed the deterministic quality gate. Fix ONLY what is
needed to make the gate pass; do not change the plan's scope.

--- GATE FAILURE OUTPUT (attempt {attempt}) ---
{gate_output}
--- END GATE FAILURE OUTPUT ---
"""


def _git_diff_files() -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            cwd=adw_common.REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.splitlines() if line]


def run(request: str, *, dry_run: bool, commit: bool) -> int:
    config = adw_common.load_config()
    planner_model = adw_common.model_for_role(config, "planner")
    builder_model = adw_common.model_for_role(config, "builder")
    max_retries = config["routing"]["retry_policy"]["max_builder_retries"]

    session_id = adw_common.new_session_id()
    logger = adw_common.PhaseLogger(session_id)
    handoff = adw_common.handoff_dir(session_id)
    logger.info(f"session_id={session_id} max_builder_retries={max_retries}")

    # --- Phase 1: Planner (Tier 1) ---
    logger.phase_start("planner", "planner", planner_model)
    ok, plan_text = adw_common.run_claude(
        PLANNER_PROMPT_TEMPLATE.format(request=request),
        planner_model,
        dry_run=dry_run,
    )
    plan_path = handoff / "plan.md"
    plan_json_path = handoff / "plan.json"
    if dry_run:
        plan_text = f"<dry-run placeholder plan for: {request}>\n"
    adw_common.write_text(plan_path, plan_text)
    adw_common.write_envelope(
        plan_json_path,
        status="dry-run" if dry_run else ("ok" if ok else "error"),
        summary=f"plan for: {request}",
        changed_files=[],
    )
    logger.phase_end("planner", dry_run or ok)
    if not dry_run and not ok:
        logger.info("planner phase failed; aborting before builder")
        return 1

    # --- Phase 2: Builder (Tier 2) with bounded retry ---
    attempt = 0
    gate_result: dict = {}
    while True:
        attempt += 1
        logger.phase_start(f"builder(attempt {attempt})", "builder", builder_model)

        retry_context = ""
        if attempt > 1:
            retry_context = RETRY_CONTEXT_TEMPLATE.format(
                attempt=attempt - 1, gate_output=json.dumps(gate_result, indent=2, default=str)
            )
        builder_prompt = BUILDER_PROMPT_TEMPLATE.format(plan=plan_text, retry_context=retry_context)

        ok, builder_output = adw_common.run_claude(builder_prompt, builder_model, dry_run=dry_run)
        envelope_path = handoff / "envelope.json"
        changed_files = [] if dry_run else _git_diff_files()
        adw_common.write_envelope(
            envelope_path,
            status="dry-run" if dry_run else ("ok" if ok else "error"),
            summary=f"builder attempt {attempt} for: {request}",
            changed_files=changed_files,
            commit_message=f"{request} (session {session_id}, attempt {attempt})",
        )
        logger.phase_end(f"builder(attempt {attempt})", dry_run or ok)

        # --- Phase 3: Deterministic gate (Tier 3) ---
        if dry_run:
            logger.info("[dry-run] would run: adws/gates.py quality")
            logger.info("[dry-run] skipping retry loop and commit; plan/build phases printed above")
            return 0

        gate_result = gates.code_quality()
        (handoff / "gate_results.json").write_text(json.dumps(gate_result, indent=2, default=str))
        (handoff / "test_log.txt").write_text(json.dumps(gate_result.get("detail", {}), indent=2, default=str))
        logger.gate_result(gate_result)

        if gate_result["pass"]:
            break

        if attempt >= max_retries:
            escalation = {
                "status": "escalated",
                "summary": f"builder exhausted {max_retries} retries; escalating to planner",
                "changed_files": changed_files,
                "last_gate_result": gate_result,
            }
            (handoff / "escalation.json").write_text(json.dumps(escalation, indent=2, default=str))
            logger.info(f"retries exhausted ({attempt}/{max_retries}); escalating to planner (see escalation.json)")
            return 1

        logger.info(f"gate failed on attempt {attempt}/{max_retries}; retrying builder with gate output")

    # --- Phase 4: git commit (Tier 3, deterministic) ---
    if commit:
        logger.phase_start("git_commit", "git_commit", "n/a (deterministic)")
        subprocess.run(["git", "add", "-A"], cwd=adw_common.REPO_ROOT, check=False)
        subprocess.run(
            ["git", "commit", "-m", f"{request}\n\nSession: {session_id}"],
            cwd=adw_common.REPO_ROOT,
            check=False,
        )
        logger.phase_end("git_commit", True)
    else:
        logger.info("commit skipped (--no-commit); changes left staged in working tree")

    logger.info(f"adw_plan_build_test succeeded in {attempt} attempt(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="adw_plan_build_test: Planner (Tier 1) -> Builder (Tier 2) -> Gate/Test (Tier 3) -> commit."
    )
    parser.add_argument("--request", required=True, help="Feature request / task description for the planner.")
    parser.add_argument("--dry-run", action="store_true", help="Print the phase plan/commands; invoke no LLM.")
    parser.add_argument(
        "--no-commit", action="store_true", help="Skip the final git commit phase even on gate success."
    )
    args = parser.parse_args(argv)
    return run(args.request, dry_run=args.dry_run, commit=not args.no_commit)


if __name__ == "__main__":
    sys.exit(main())
