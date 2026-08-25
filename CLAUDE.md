# BrineGuard Coast — project contract

Communication contract for Tier 1 (SOTA) sessions — follow it in every response:
@agent-system-prompt.md

GPIW 2026 Track A submission, deadline 2026-09-30. **BUILD_PLAN.md is canonical**;
work proceeds phase-by-phase (§10) with commits as the progress log.

## Operating model (SSSF)

This repo runs a Super Simple Software Factory (`adws/SSSF_SPEC.md`; routing in
`sssf.config.yaml`). Route work to the cheapest reliable actor:

- **Tier 1 (orchestrator session)**: plans, dispatches, reviews diffs, evaluates
  results. It does NOT implement feature code — implementation goes to Workhorse
  builders via Orca (`orca orchestration` task-create → worker-start → check --wait,
  or `tools/orca_dispatch.py` once present).
- **Tier 2 (Workhorse builders/scouts/documenters)**: implement exactly the
  dispatched spec, no scope expansion. Default builder: pi × deepseek/deepseek-v4-pro.
- **Tier 3 (deterministic code, zero tokens)**: all verification. Never ask a model
  to check what code can check.

## Commands

- Tests: `.venv/bin/python -m pytest -q` (suite runs ~2 s — run it before declaring
  anything done)
- Quality gate: `.venv/bin/python adws/gates.py quality --python .venv/bin/python`
- Standard run: `.venv/bin/python -m brineguard run-first-slice -c configs/first_slice.yaml`
- Fleet probe: `python3 tools/probe.py` · orientation: `bash tools/session_brief.sh`

## Rules

- Reusable tools over ad-hoc snippets: check `tools/README.md` first; extend a
  template-table tool (e.g. `tools/probe.py`) rather than writing a one-off check.
- Run artifacts follow the contract in `src/brineguard/experiments/runner.py`;
  never hand-edit `runs/`.
- Keys live in gitignored `.env*` files and must never appear in code, argv, or logs.
- Linearity of the transport kernel is an architectural invariant (BUILD_PLAN §5.2).
