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

- **VERIFY, DON'T GUESS.** Never answer a factual question from recall or by
  probing guessed values (version numbers, flag names, IDs). For "what is the
  latest X": web-search `latest model by <company name>` FIRST, then confirm
  availability in the actual catalog/CLI. When grepping a catalog, list the
  whole family — never filter by a guessed version substring.

- **Precedence when rules conflict:** evidence integrity > the current task's
  explicit contract > deterministic gates > scope > latency/concision. Never
  weaken a higher rule silently to meet a lower one — say PARTIAL or
  VERIFICATION-PENDING instead. User-supplied and repo-authoritative context
  count as evidence (no redundant re-retrieval); after one failed bounded
  retrieval, give the known answer labeled UNVERIFIED and name the missing source.

- **Review labels are load-tested words.** A thinking-low or wording-scoped
  pass is a WORDING-CHECK and may never be reported as adversarial,
  independent, agreed, or final. "Final/agreed" requires an adversarial pass
  (rewarded-per-flaw framing, thinking medium+) whose prompt embedded the
  claim sources. Name the exact check performed ("character-count verified"),
  never a bare "verified".

- Reusable tools over ad-hoc snippets: check `tools/README.md` first; extend a
  template-table tool (e.g. `tools/probe.py`) rather than writing a one-off check.
- Run artifacts follow the contract in `src/brineguard/experiments/runner.py`;
  never hand-edit `runs/`.
- Keys live in gitignored `.env*` files and must never appear in code, argv, or logs.
- Linearity of the transport kernel is an architectural invariant (BUILD_PLAN §5.2).
