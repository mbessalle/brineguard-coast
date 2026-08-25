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


def run(request: str, *, dry_run: bool, commit: bool) -> int:
    config = adw_common.load_config()
    planner_model = adw_common.model_for_role(config, "planner")

    session_id = adw_common.new_session_id()
    logger = adw_common.PhaseLogger(session_id)
    handoff = adw_common.handoff_dir(session_id)
    logger.info(f"session_id={session_id}")

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
        status="succeeded" if (dry_run or ok) else "failed",
        summary=f"plan for: {request}",
        changed_files=[],
    )
    # Validate planner envelope BEFORE proceeding
    plan_gate = gates.json_parse(str(plan_json_path))
    logger.gate_result(plan_gate)
    logger.phase_end("planner", plan_gate["pass"])
    if not plan_gate["pass"]:
        logger.info("planner envelope gate failed; aborting")
        return 1

    # --- Phase 2: Builder (Tier 2) with retry ladder ---
    rc, builder_output, total_attempts = adw_common.retry_ladder(
        "builder",
        BUILDER_PROMPT_TEMPLATE,
        plan_text=plan_text,
        dry_run=dry_run,
        logger=logger,
        handoff=handoff,
        config=config,
    )
    if dry_run:
        return 0
    if rc != 0:
        escalation = {
            "status": "failed",
            "summary": f"builder exhausted all rungs after {total_attempts} attempts; see escalation.json",
            "changed_files": adw_common._git_diff_files(),
            "total_attempts": total_attempts,
        }
        (handoff / "escalation.json").write_text(json.dumps(escalation, indent=2, default=str))
        logger.info(f"builder failed after {total_attempts} attempt(s); escalation written")
        return 1

    # --- Phase 3: git commit (Tier 3, deterministic) ---
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

    logger.info(f"adw_plan_build_test succeeded in {total_attempts} attempt(s)")
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
