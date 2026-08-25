---
name: fh-harness
description: Supporting harness commands and principles from system-orchestration.md — auto-validate (test gates first), per-slot system prompts, context reset, TIL-Done status board, tier strategy, and the effective-agent-hour-per-token-cost metric. Load when applying or explaining the multi-agent harness conventions.
---

# /fh-harness — Supporting Commands & Principles

From system-orchestration.md §1, §2, §4.

## Principles

- **AND over OR:** combine complementary models across tiers instead of
  selecting one. Optimize the trade-off triangle (performance / speed / cost);
  the metric is **effective agent-hours per token cost**.
- **Anonymization:** aliases in `sssf.config.yaml anonymization.aliases`;
  real model names never reach peer agents.
- **Evolution target:** out-loop software factory (autonomous pipelines +
  gates), not in-loop prompt babysitting.
- Tiers: SOTA = architect/orchestrator (this session); Workhorse = builders/
  scouts per `routes`; Lightweight local tier not installed yet (see config
  note) — nearest equivalent is the scout route.

## Commands

- **fh-auto-validate:** write the test gate FIRST (a failing pytest test or a
  gates.py check), then dispatch builders instructed to iterate until it exits
  0. Existing machinery: `adws/gates.py`, the bounded retry loop in
  `adws/adw_plan_build_test.py`, and the PostToolUse pytest hook.
- **fh-system-prompt:** per-slot prompt injection — `run_route(...,
  role_prompt_override=...)` in `adws/adw_common.py`, `--append-system-prompt`
  for pi, `-s` for the openrouter-api backend.
- **fh-reset:** fresh context per dispatch is the default (pi `--no-session`,
  new Orca terminals per worker). For a stuck/contaminated worker: release it
  and start a fresh dispatch rather than steering a long context.
- **TIL-Done tracker:** `orca orchestration task-list --brief --json` is the
  shared status board (pending/ready/dispatched/completed/failed/blocked);
  `python3 tools/orca_dispatch.py status` prints it.
