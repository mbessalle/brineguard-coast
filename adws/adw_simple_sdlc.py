#!/usr/bin/env python3
"""adw_simple_sdlc: Request -> Plan (SOTA) -> Build (Workhorse) -> Test
(Deterministic) -> Review (SOTA) -> Document (Workhorse) -> Commit.

Full SDLC pipeline from sssf.config.yaml `workflows.adw_simple_sdlc`.
Mirrors adw_plan_build_test.py's structure, logging, envelope writing,
bounded retry policy, and flags.

Usage:
    .venv/bin/python adws/adw_simple_sdlc.py --request "add X" --dry-run
    .venv/bin/python adws/adw_simple_sdlc.py --request "add X"

Output (adw_data/sessions/<session_id>/context_handoff/):
    plan.md, plan.json                (planner)
    envelope.json                      (builder, last attempt)
    gate_results.json, test_log.txt    (deterministic gate)
    review.md, review.json             (reviewer, independent route)
    docs_envelope.json                 (documenter)
    escalation.json                    (only if retries exhausted)
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

REVIEWER_PROMPT_TEMPLATE = """You are the Reviewer in an SSSF pipeline (Tier 1, independent second opinion).

Review this implementation against the plan. You did not write it; be skeptical.

--- PLAN ---
{plan}
--- END PLAN ---

--- BUILDER SUMMARY ---
{summary}
--- END BUILDER SUMMARY ---

Hunt for: correctness bugs with concrete failure scenarios, spec deviations,
silent scope creep, missing tests, violated invariants. Rank findings most-severe
first. State the failure scenario for each (inputs -> wrong outcome).

Verdict line first: APPROVE or REQUEST-CHANGES with the one-sentence reason.
"""

DOCUMENTER_PROMPT_TEMPLATE = """You are the Documenter in an SSSF pipeline (Tier 2, Workhorse).

Produce documentation for the changes described below. Facts only from the
provided inputs — never invent behavior, numbers, or filenames.

--- PLAN ---
{plan}
--- END PLAN ---

--- BUILDER SUMMARY ---
{summary}
--- END BUILDER SUMMARY ---

--- REVIEW VERDICT ---
{review}
--- END REVIEW VERDICT ---

Lead with what changed and why it matters; details after. Complete sentences,
no jargon chains. Output Markdown suitable for a changelog or README update.
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
    builder_model = adw_common.route_model(config, "builder")
    reviewer_model = adw_common.route_model(config, "reviewer_independent")
    documenter_model = adw_common.route_model(config, "documenter")
    max_retries = config["routing"]["retry_policy"]["max_builder_retries"]

    session_id = adw_common.new_session_id()
    logger = adw_common.PhaseLogger(session_id)
    handoff = adw_common.handoff_dir(session_id)
    logger.info(f"session_id={session_id} max_builder_retries={max_retries} workflow=adw_simple_sdlc")

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
    builder_output = ""
    while True:
        attempt += 1
        logger.phase_start(f"builder(attempt {attempt})", "builder", builder_model)

        retry_context = ""
        if attempt > 1:
            retry_context = RETRY_CONTEXT_TEMPLATE.format(
                attempt=attempt - 1, gate_output=json.dumps(gate_result, indent=2, default=str)
            )
        builder_prompt = BUILDER_PROMPT_TEMPLATE.format(plan=plan_text, retry_context=retry_context)

        ok, builder_output = adw_common.run_route("builder", builder_prompt, dry_run=dry_run, logger=logger)
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
            logger.info("[dry-run] skipping retry loop; phases printed above")
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

    logger.info(f"builder succeeded in {attempt} attempt(s)")

    # --- Phase 4: Reviewer (Tier 1b, independent) ---
    logger.phase_start("reviewer", "reviewer", reviewer_model)
    builder_summary = builder_output[-2000:] if builder_output else "(no builder output)"
    reviewer_prompt = REVIEWER_PROMPT_TEMPLATE.format(plan=plan_text, summary=builder_summary)
    ok, review_output = adw_common.run_route(
        "reviewer_independent", reviewer_prompt, dry_run=dry_run, logger=logger
    )
    review_path = handoff / "review.md"
    review_json_path = handoff / "review.json"
    adw_common.write_text(review_path, review_output or "<empty review>")
    adw_common.write_envelope(
        review_json_path,
        status="dry-run" if dry_run else ("ok" if ok else "error"),
        summary=f"review of: {request}",
        changed_files=[],
        verdict=review_output[:200] if review_output else "",
    )
    logger.phase_end("reviewer", dry_run or ok)
    if not dry_run and not ok:
        logger.info("reviewer phase failed (non-fatal for commit); continuing")

    # --- Phase 5: Documenter (Tier 2) ---
    logger.phase_start("documenter", "documenter", documenter_model)
    doc_prompt = DOCUMENTER_PROMPT_TEMPLATE.format(
        plan=plan_text, summary=builder_summary, review=review_output[:2000] if review_output else "(no review)"
    )
    ok, doc_output = adw_common.run_route("documenter", doc_prompt, dry_run=dry_run, logger=logger)
    docs_path = handoff / "docs.md"
    docs_envelope_path = handoff / "docs_envelope.json"
    adw_common.write_text(docs_path, doc_output or "<empty docs>")
    adw_common.write_envelope(
        docs_envelope_path,
        status="dry-run" if dry_run else ("ok" if ok else "error"),
        summary=f"documentation for: {request}",
        changed_files=[],
    )
    logger.phase_end("documenter", dry_run or ok)

    # --- Phase 6: git commit (Tier 3, deterministic) ---
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

    logger.info(f"adw_simple_sdlc succeeded in {attempt} builder attempt(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="adw_simple_sdlc: Planner -> Builder -> Test -> Review -> Document -> Commit."
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