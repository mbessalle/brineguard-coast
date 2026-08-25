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

REVIEWER_PROMPT_TEMPLATE = """You are the Reviewer in an SSSF pipeline (Tier 1, independent second opinion).

The role prompt in adws/prompts/reviewer.md defines your review contract; follow
it exactly. Review this implementation against the plan and the full git diff.

--- PLAN ---
{plan}
--- END PLAN ---

--- FULL GIT DIFF ---
{diff}
--- END GIT DIFF ---

--- CHANGED FILES ---
{changed_files}
--- END CHANGED FILES ---

Hunt for: correctness bugs with concrete failure scenarios, spec deviations,
silent scope creep, missing tests, violated invariants. Rank findings most-severe
first. Your verdict line MUST start with one of APPROVE, REQUEST-CHANGES, PARTIAL,
or BLOCKED followed by a one-sentence reason.
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


def run(request: str, *, dry_run: bool, commit: bool) -> int:
    config = adw_common.load_config()
    planner_model = adw_common.model_for_role(config, "planner")
    reviewer_model = adw_common.route_model(config, "reviewer_independent")
    documenter_model = adw_common.route_model(config, "documenter")

    session_id = adw_common.new_session_id()
    logger = adw_common.PhaseLogger(session_id)
    handoff = adw_common.handoff_dir(session_id)
    logger.info(f"session_id={session_id} workflow=adw_simple_sdlc")

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

    logger.info(f"builder succeeded in {total_attempts} attempt(s)")

    # --- Phase 3: Reviewer (Tier 1b, independent) ---
    logger.phase_start("reviewer", "reviewer", reviewer_model)
    git_diff = adw_common._git_diff_full()
    changed_files = adw_common._git_diff_files()

    # Abort review (and never commit) if evidence is missing/empty.
    if not plan_text.strip() or git_diff in ("", "(no changes)", "(git diff unavailable)", "(git diff failed)"):
        reason = "missing plan" if not plan_text.strip() else "missing/empty git diff"
        logger.info(f"BLOCKED-INCOMPLETE-INPUT: {reason}; aborting before review")
        adw_common.write_envelope(
            handoff / "review.json",
            status="failed",
            summary=f"BLOCKED-INCOMPLETE-INPUT: {reason}",
            changed_files=[],
            verdict="BLOCKED",
        )
        logger.phase_end("reviewer", False)
        return 1

    reviewer_prompt = REVIEWER_PROMPT_TEMPLATE.format(
        plan=plan_text, diff=git_diff, changed_files="\n".join(changed_files),
    )
    ok, review_output = adw_common.run_route(
        "reviewer_independent", reviewer_prompt, dry_run=dry_run, logger=logger
    )

    # Parse verdict from reviewer output
    try:
        verdict, reason = adw_common.parse_verdict(review_output)
    except ValueError as exc:
        verdict, reason = "BLOCKED", str(exc)

    review_path = handoff / "review.md"
    review_json_path = handoff / "review.json"
    adw_common.write_text(review_path, review_output or "<empty review>")
    adw_common.write_envelope(
        review_json_path,
        status="succeeded" if (dry_run or ok) else "failed",
        summary=f"{verdict}: {reason}" if reason else verdict,
        changed_files=[],
        verdict=verdict,
    )

    # Validate reviewer envelope
    review_gate = gates.json_parse(str(review_json_path))
    logger.gate_result(review_gate)
    logger.phase_end("reviewer", dry_run or ok)

    # Verdict control flow
    if verdict == "APPROVE":
        logger.info("reviewer APPROVED; advancing to documenter")
    elif verdict == "REQUEST-CHANGES":
        logger.info(f"reviewer REQUEST-CHANGES: {reason}; feeding back to builder retry ladder")
        # Feed review findings back to builder as first-attempt context; the
        # quality gate still runs normally (no extra_gate_fn here).
        review_builder_template = (
            "You are the Builder in an SSSF pipeline (Tier 2, Workhorse).\n\n"
            "The reviewer requested changes. Fix ONLY the issues below; do not "
            "change the plan's scope.\n\n"
            "--- PLAN ---\n{plan}\n--- END PLAN ---\n"
            f"--- REVIEWER FEEDBACK ---\n{reason}\n--- END REVIEWER FEEDBACK ---\n"
            "{retry_context}"
        )
        rc2, builder_output, total2 = adw_common.retry_ladder(
            "builder",
            review_builder_template,
            plan_text=plan_text,
            dry_run=dry_run,
            logger=logger,
            handoff=handoff,
            config=config,
        )
        if rc2 != 0:
            logger.info("builder failed on REQUEST-CHANGES retry; aborting")
            return 1
        logger.info("builder passed after REQUEST-CHANGES retry")
        # Re-run reviewer after fix
        git_diff = adw_common._git_diff_full()
        changed_files = adw_common._git_diff_files()
        reviewer_prompt2 = REVIEWER_PROMPT_TEMPLATE.format(
            plan=plan_text, diff=git_diff, changed_files="\n".join(changed_files),
        )
        ok, review_output = adw_common.run_route(
            "reviewer_independent", reviewer_prompt2, dry_run=dry_run, logger=logger
        )
        try:
            verdict, reason = adw_common.parse_verdict(review_output)
        except ValueError:
            verdict, reason = "BLOCKED", "unparseable verdict on re-review"
        adw_common.write_text(review_path, review_output or "<empty review>")
        adw_common.write_envelope(
            review_json_path,
            status="succeeded" if ok else "failed",
            summary=f"{verdict}: {reason}" if reason else verdict,
            changed_files=[],
            verdict=verdict,
        )
        if verdict != "APPROVE":
            logger.info(f"re-review verdict {verdict}: {reason}; aborting")
            return 1
        logger.info("re-review APPROVED; advancing to documenter")
    else:
        logger.info(f"reviewer verdict {verdict}: {reason}; aborting (not APPROVE or REQUEST-CHANGES)")
        return 1

    # --- Phase 4: Documenter (Tier 2) ---
    logger.phase_start("documenter", "documenter", documenter_model)
    doc_prompt = DOCUMENTER_PROMPT_TEMPLATE.format(
        plan=plan_text,
        summary=builder_output[-2000:] if builder_output else "(no builder output)",
        review=review_output[:2000] if review_output else "(no review)",
    )
    ok, doc_output = adw_common.run_route("documenter", doc_prompt, dry_run=dry_run, logger=logger)
    docs_path = handoff / "docs.md"
    docs_envelope_path = handoff / "docs_envelope.json"
    adw_common.write_text(docs_path, doc_output or "<empty docs>")
    adw_common.write_envelope(
        docs_envelope_path,
        status="succeeded" if (dry_run or ok) else "failed",
        summary=f"documentation for: {request}",
        changed_files=[],
    )
    # Validate documenter envelope
    doc_gate = gates.json_parse(str(docs_envelope_path))
    logger.gate_result(doc_gate)
    logger.phase_end("documenter", doc_gate["pass"])
    if not doc_gate["pass"]:
        logger.info("documenter envelope gate failed")

    # --- Phase 5: git commit (Tier 3, deterministic) ---
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

    logger.info(f"adw_simple_sdlc succeeded in {total_attempts} builder attempt(s)")
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