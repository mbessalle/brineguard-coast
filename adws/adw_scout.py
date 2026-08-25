#!/usr/bin/env python3
"""adw_scout: fast, read-only recon on the codebase/architecture.

Single-phase workflow. Routes to the Tier 2 Workhorse "scout" model (see
sssf.config.yaml). Runs with a restricted, read-only permission mode and
performs no state mutation: no file edits, no git operations.

Usage:
    .venv/bin/python adws/adw_scout.py --topic "how does the dispatch model work?"
    .venv/bin/python adws/adw_scout.py --topic "..." --dry-run

Output:
    adw_data/sessions/<session_id>/context_handoff/scout_findings.md
    adw_data/sessions/<session_id>/context_handoff/envelope.json
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import adw_common  # noqa: E402
import gates  # noqa: E402

SCOUT_PROMPT_TEMPLATE = """You are the Scout in an SSSF (Super Simple Software Factory) pipeline.

Perform fast, READ-ONLY recon in this repository to answer the topic below.
Do not edit any files. Do not run git commands that mutate state. Only
inspect the codebase (read files, grep, list directories) and summarize.

Topic: {topic}

Respond with a concise Markdown report covering:
- Relevant files/modules (with paths)
- Key architectural facts relevant to the topic
- Anything that looks risky or ambiguous for a future planner/builder phase
"""


def run(topic: str, *, dry_run: bool) -> int:
    config = adw_common.load_config()
    model = adw_common.route_model(config, "scout")
    session_id = adw_common.new_session_id()
    logger = adw_common.PhaseLogger(session_id)
    handoff = adw_common.handoff_dir(session_id)

    logger.info(f"session_id={session_id}")
    logger.phase_start("scout", "scout", model)

    prompt = SCOUT_PROMPT_TEMPLATE.format(topic=topic)
    ok, output = adw_common.run_route("scout", prompt, dry_run=dry_run, logger=logger)

    findings_path = handoff / "scout_findings.md"
    envelope_path = handoff / "envelope.json"

    if dry_run:
        logger.info(f"[dry-run] would write {findings_path}")
        logger.info(f"[dry-run] would write {envelope_path}")
        adw_common.write_text(findings_path, f"<dry-run placeholder for topic: {topic}>\n")
        adw_common.write_envelope(
            envelope_path,
            status="dry-run",
            summary=f"dry-run scout of: {topic}",
            changed_files=[],
        )
        logger.phase_end("scout", True)
        logger.info("[dry-run] skipping gate execution")
        return 0

    adw_common.write_text(findings_path, output)
    adw_common.write_envelope(
        envelope_path,
        status="ok" if ok else "error",
        summary=f"scout recon on: {topic}",
        changed_files=[],  # scout is read-only by contract
    )
    logger.phase_end("scout", ok)

    gate_results = [
        gates.artifacts_exist([str(findings_path), str(envelope_path)]),
        gates.files_non_empty([str(findings_path), str(envelope_path)]),
        gates.json_parse(str(envelope_path)),
    ]
    for result in gate_results:
        logger.gate_result(result)

    all_pass = ok and all(r["pass"] for r in gate_results)
    logger.info(f"scout {'succeeded' if all_pass else 'failed'}; findings at {findings_path}")
    return 0 if all_pass else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="adw_scout: fast, read-only recon on codebase/architecture (Tier 2 Workhorse)."
    )
    parser.add_argument("--topic", default="general architecture overview", help="What to recon.")
    parser.add_argument("--dry-run", action="store_true", help="Print the phase plan/commands; invoke no LLM.")
    args = parser.parse_args(argv)
    return run(args.topic, dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
