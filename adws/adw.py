#!/usr/bin/env python3
"""ADW chain menu: one launcher over the full SSSF composability ladder.

Every chain is DATA (the CHAINS table below): a name mapped to an ordered
list of phase steps plus a use-when note. Execution composes the already
hardened machinery by import — adw_common.run_route / retry_ladder /
envelope helpers, gates.code_quality / json_parse for code() phases, and the
existing end-to-end modules for adw_plan_build_test / adw_simple_sdlc.

Usage:
    python3 adws/adw.py --list
    python3 adws/adw.py run <name> --request "..." [--dry-run] [--no-commit]
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
import adw_plan_build_test  # noqa: E402
import adw_simple_sdlc  # noqa: E402
from adw_scout import SCOUT_PROMPT_TEMPLATE  # noqa: E402
from adw_plan_build_test import PLANNER_PROMPT_TEMPLATE, BUILDER_PROMPT_TEMPLATE  # noqa: E402
from adw_simple_sdlc import REVIEWER_PROMPT_TEMPLATE, DOCUMENTER_PROMPT_TEMPLATE  # noqa: E402

REPO_ROOT = adw_common.REPO_ROOT

# ---------------------------------------------------------------------------
# The composability ladder. "engineer" (the human/coordinator that picks a
# chain) is implicit; `phases` is the ordered machine-executed step list.
# The "[-> builder(fix/revise) ... bounded]" retry annotations in the spec
# are not phases — they are the retry_ladder semantics already baked into
# the builder step.
# ---------------------------------------------------------------------------
CHAINS: dict[str, dict] = {
    "adw_prompt": {
        "phases": ["<agent>"],
        "use_when": "one agent, one prompt, traced end-to-end - the smallest unit",
    },
    "adw_scout": {
        "phases": ["scout"],
        "use_when": "read-only recon; nothing changes",
    },
    "adw_plan": {
        "phases": ["planner"],
        "use_when": "you want the plan reviewed before any code moves",
    },
    "adw_build": {
        "phases": ["builder"],
        "use_when": "the change is well understood; just do it",
    },
    "adw_quality": {
        "phases": ["code(quality)"],
        "use_when": "deterministic checks only (lint/format/typecheck)",
    },
    "adw_document": {
        "phases": ["code(changes)", "documenter"],
        "use_when": "write up work already done, from git diff vs main",
    },
    "adw_plan_build": {
        "phases": ["planner", "builder", "git(commit)"],
        "use_when": "real change worth planning, then shipping as one commit",
    },
    "adw_build_test": {
        "phases": ["builder", "code(test)"],
        "use_when": "code exists to build and a test command to prove it",
    },
    "adw_build_review": {
        "phases": ["builder", "reviewer"],
        "use_when": "correctness-of-intent matters more than tests",
    },
    "adw_plan_build_test": {
        "phases": ["planner", "builder", "code(test)", "git(commit)"],
        "use_when": "the default full loop for a nontrivial change",
    },
    "adw_plan_build_test_quality": {
        "phases": ["planner", "builder", "code(verify)", "code(test)", "git(commit)"],
        "use_when": "same, plus quality gates before the commit",
    },
    "adw_simple_sdlc": {
        "phases": [
            "planner", "git(commit_plan)", "builder", "code(test)",
            "reviewer", "documenter", "git(commit)",
        ],
        "use_when": "the work is real and its shape is not obvious",
    },
}

# Chains already implemented end-to-end elsewhere: delegate, don't duplicate.
DELEGATED_MODULES = {
    "adw_plan_build_test": adw_plan_build_test,
    "adw_simple_sdlc": adw_simple_sdlc,
}


def _chain_str(entry: dict) -> str:
    return "engineer -> " + " -> ".join(entry["phases"])


def print_chain_list() -> None:
    """Print the ADW / Chain / Use when table (all 12 chains)."""
    name_w = max(len(n) for n in CHAINS)
    chain_w = max(len(_chain_str(e)) for e in CHAINS.values())
    header = f"{'ADW':<{name_w}}  {'Chain':<{chain_w}}  {'Use when'}"
    print(header)
    print("-" * len(header))
    for name, entry in CHAINS.items():
        print(f"{name:<{name_w}}  {_chain_str(entry):<{chain_w}}  {entry['use_when']}")


def _print_phase_list(name: str, entry: dict) -> None:
    print(f"[dry-run] chain={name}")
    print(f"[dry-run] phases: {_chain_str(entry)}")
    for phase in entry["phases"]:
        print(f"[dry-run]   - {phase}")


# ---------------------------------------------------------------------------
# Phase runners — thin adapters over the hardened machinery. They mutate a
# shared ctx dict and return 0 on success, nonzero on failure.
# ---------------------------------------------------------------------------

def _run_scout(ctx: dict) -> int:
    config, logger, handoff = ctx["config"], ctx["logger"], ctx["handoff"]
    model = adw_common.route_model(config, "scout")
    logger.phase_start("scout", "scout", model)
    prompt = SCOUT_PROMPT_TEMPLATE.format(topic=ctx["request"])
    ok, output = adw_common.run_route("scout", prompt, dry_run=False, logger=logger)
    adw_common.write_text(handoff / "scout_findings.md", output)
    adw_common.write_envelope(
        handoff / "envelope.json",
        status="succeeded" if ok else "failed",
        summary=f"scout recon on: {ctx['request']}",
        changed_files=[],
    )
    logger.phase_end("scout", ok)
    return 0 if ok else 1


def _run_planner(ctx: dict) -> int:
    config, logger, handoff = ctx["config"], ctx["logger"], ctx["handoff"]
    planner_model = adw_common.model_for_role(config, "planner")
    logger.phase_start("planner", "planner", planner_model)
    ok, plan = adw_common.run_claude(
        PLANNER_PROMPT_TEMPLATE.format(request=ctx["request"]),
        planner_model,
        dry_run=False,
    )
    adw_common.write_text(handoff / "plan.md", plan)
    adw_common.write_envelope(
        handoff / "plan.json",
        status="succeeded" if ok else "failed",
        summary=f"plan for: {ctx['request']}",
        changed_files=[],
    )
    gate = gates.json_parse(str(handoff / "plan.json"))
    logger.gate_result(gate)
    logger.phase_end("planner", gate["pass"])
    ctx["plan_text"] = plan
    return 0 if gate["pass"] else 1


def _run_builder(ctx: dict) -> int:
    config, logger, handoff = ctx["config"], ctx["logger"], ctx["handoff"]
    plan = ctx.get("plan_text") or ctx["request"]
    rc, output, _ = adw_common.retry_ladder(
        "builder",
        BUILDER_PROMPT_TEMPLATE,
        plan_text=plan,
        dry_run=False,
        logger=logger,
        handoff=handoff,
        config=config,
    )
    ctx["builder_output"] = output
    return rc


def _run_code_gate(ctx: dict) -> int:
    logger, handoff = ctx["logger"], ctx["handoff"]
    logger.phase_start("code", "code", "n/a (deterministic)")
    result = gates.code_quality()
    (handoff / "gate_results.json").write_text(json.dumps(result, indent=2, default=str))
    logger.gate_result(result)
    logger.phase_end("code", result["pass"])
    return 0 if result["pass"] else 1


def _run_code_changes(ctx: dict) -> int:
    logger = ctx["logger"]
    logger.phase_start("code(changes)", "code", "n/a (deterministic)")
    ctx["git_diff"] = adw_common._git_diff_full()
    logger.phase_end("code(changes)", True)
    return 0


def _run_reviewer(ctx: dict) -> int:
    config, logger, handoff = ctx["config"], ctx["logger"], ctx["handoff"]
    model = adw_common.route_model(config, "reviewer_independent")
    logger.phase_start("reviewer", "reviewer", model)
    plan = ctx.get("plan_text") or ctx["request"]
    diff = ctx.get("git_diff") or adw_common._git_diff_full()
    changed = adw_common._git_diff_files()
    prompt = REVIEWER_PROMPT_TEMPLATE.format(
        plan=plan, diff=diff, changed_files="\n".join(changed),
    )
    ok, output = adw_common.run_route("reviewer_independent", prompt, dry_run=False, logger=logger)
    try:
        verdict, reason = adw_common.parse_verdict(output)
    except ValueError as exc:
        verdict, reason = "BLOCKED", str(exc)
    adw_common.write_text(handoff / "review.md", output or "<empty review>")
    adw_common.write_envelope(
        handoff / "review.json",
        status="succeeded" if ok else "failed",
        summary=f"{verdict}: {reason}" if reason else verdict,
        changed_files=[],
        verdict=verdict,
    )
    gate = gates.json_parse(str(handoff / "review.json"))
    logger.gate_result(gate)
    passed = ok and verdict == "APPROVE" and gate["pass"]
    logger.phase_end("reviewer", passed)
    ctx["review_output"] = output
    return 0 if passed else 1


def _run_documenter(ctx: dict) -> int:
    config, logger, handoff = ctx["config"], ctx["logger"], ctx["handoff"]
    model = adw_common.route_model(config, "documenter")
    logger.phase_start("documenter", "documenter", model)
    summary = ctx.get("git_diff") or ctx.get("builder_output") or "(no changes)"
    prompt = DOCUMENTER_PROMPT_TEMPLATE.format(
        plan=ctx.get("plan_text") or "(no plan; changes already made)",
        summary=summary,
        review=ctx.get("review_output") or "(no review)",
    )
    ok, output = adw_common.run_route("documenter", prompt, dry_run=False, logger=logger)
    adw_common.write_text(handoff / "docs.md", output or "<empty docs>")
    adw_common.write_envelope(
        handoff / "docs_envelope.json",
        status="succeeded" if ok else "failed",
        summary=f"documentation for: {ctx['request']}",
        changed_files=[],
    )
    logger.phase_end("documenter", ok)
    return 0 if ok else 1


def _run_git_commit(ctx: dict) -> int:
    logger = ctx["logger"]
    if not ctx.get("commit", True):
        logger.info("commit skipped (--no-commit); changes left in working tree")
        return 0
    logger.phase_start("git(commit)", "git", "n/a (deterministic)")
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=False)
    subprocess.run(
        ["git", "commit", "-m", f"{ctx['request']}\n\nSession: {ctx['session_id']}"],
        cwd=REPO_ROOT, check=False,
    )
    logger.phase_end("git(commit)", True)
    return 0


def _run_git_commit_plan(ctx: dict) -> int:
    logger = ctx["logger"]
    if not ctx.get("commit", True):
        logger.info("commit_plan skipped (--no-commit)")
        return 0
    logger.phase_start("git(commit_plan)", "git", "n/a (deterministic)")
    subprocess.run(["git", "add", "-A"], cwd=REPO_ROOT, check=False)
    subprocess.run(
        ["git", "commit", "-m", f"plan: {ctx['request']}\n\nSession: {ctx['session_id']}"],
        cwd=REPO_ROOT, check=False,
    )
    logger.phase_end("git(commit_plan)", True)
    return 0


def _run_agent(ctx: dict) -> int:
    config, logger, handoff = ctx["config"], ctx["logger"], ctx["handoff"]
    role = ctx.get("role") or "builder"
    model = adw_common.route_model(config, role)
    logger.phase_start("agent", role, model)
    ok, output = adw_common.run_route(role, ctx["request"], dry_run=False, logger=logger)
    adw_common.write_text(handoff / "agent_output.md", output)
    adw_common.write_envelope(
        handoff / "envelope.json",
        status="succeeded" if ok else "failed",
        summary=f"agent({role}): {ctx['request']}",
        changed_files=[],
    )
    logger.phase_end("agent", ok)
    return 0 if ok else 1


_PHASE_RUNNERS = {
    "<agent>": _run_agent,
    "scout": _run_scout,
    "planner": _run_planner,
    "builder": _run_builder,
    "reviewer": _run_reviewer,
    "documenter": _run_documenter,
    "code(quality)": _run_code_gate,
    "code(test)": _run_code_gate,
    "code(verify)": _run_code_gate,
    "code(changes)": _run_code_changes,
    "git(commit)": _run_git_commit,
    "git(commit_plan)": _run_git_commit_plan,
}


def run_chain(
    name: str,
    request: str,
    *,
    dry_run: bool,
    commit: bool = True,
    role: str | None = None,
) -> int:
    entry = CHAINS.get(name)
    if entry is None:
        print(f"ERROR: unknown chain '{name}'", file=sys.stderr)
        print_chain_list()
        return 1

    if dry_run:
        _print_phase_list(name, entry)
        return 0

    # AC5: chains already built end-to-end delegate to their own module.
    if name in DELEGATED_MODULES:
        return DELEGATED_MODULES[name].run(request, dry_run=False, commit=commit)

    config = adw_common.load_config()
    session_id = adw_common.new_session_id()
    logger = adw_common.PhaseLogger(session_id)
    handoff = adw_common.handoff_dir(session_id)
    logger.info(f"session_id={session_id} chain={name}")

    ctx = {
        "request": request,
        "config": config,
        "session_id": session_id,
        "logger": logger,
        "handoff": handoff,
        "commit": commit,
        "role": role,
        "plan_text": "",
        "builder_output": "",
        "review_output": "",
        "git_diff": "",
    }

    for phase in entry["phases"]:
        rc = _PHASE_RUNNERS[phase](ctx)
        if rc != 0:
            logger.info(f"chain {name} halted at phase {phase} (rc={rc})")
            return rc
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="adw.py",
        description="ADW chain menu: one launcher over the full SSSF composability ladder.",
    )
    parser.add_argument("--list", action="store_true", help="Print the ADW / Chain / Use when table.")
    sub = parser.add_subparsers(dest="command")
    p_run = sub.add_parser("run", help="Run one chain.")
    p_run.add_argument("name", help="Chain name (see --list).")
    p_run.add_argument("--request", required=True, help="Feature request / task text.")
    p_run.add_argument("--dry-run", action="store_true", help="Print the phase list; invoke nothing.")
    p_run.add_argument("--no-commit", action="store_true", help="Skip the final git commit phase.")
    p_run.add_argument("--role", default=None, help="Route name for the <agent> phase (adw_prompt).")
    args = parser.parse_args(argv)

    if args.list:
        print_chain_list()
        return 0
    if args.command == "run":
        return run_chain(
            args.name,
            args.request,
            dry_run=args.dry_run,
            commit=not args.no_commit,
            role=args.role,
        )
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
