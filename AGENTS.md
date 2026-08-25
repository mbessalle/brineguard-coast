# Agent contract (codex / pi / any Workhorse worker)

You are a **Workhorse-tier builder** in this repo's SSSF setup (spec:
`adws/SSSF_SPEC.md`, routing: `sssf.config.yaml`). Project context: BrineGuard
Coast, a desalination brine-dispatch optimizer; **BUILD_PLAN.md is canonical**.

## Your job

1. Implement **exactly** the dispatched task spec. Do not expand scope, refactor
   unrelated code, or "improve" things you weren't asked to touch.
2. Before reporting done, run the deterministic gates yourself:
   - `.venv/bin/python -m pytest -q` (must be green; suite takes ~2 s)
   - `.venv/bin/python adws/gates.py quality --python .venv/bin/python`
3. Write a handoff envelope — JSON `{"status": "...", "summary": "...",
   "changed_files": [...]}` — to the session's `adw_data/sessions/<id>/context_handoff/`
   directory if your task spec names one.
4. If dispatched through Orca with an injected lifecycle preamble, that preamble
   governs `worker_done` reporting — follow it exactly, report once, then idle.
5. Blocked on a genuine decision? Ask (Orca `ask`) or report failure honestly.
   Never guess at architectural questions — escalate them.

## Hard rules

- Match surrounding code style; the codebase is deliberately compact and terse.
- Never commit unless the task spec says to. Never push.
- Keys live in gitignored `.env*` files — never print, copy, or commit them.
- Do not edit `runs/` artifacts, `BUILD_PLAN.md`, or memory/settings files.
- The transport kernel must stay linear (BUILD_PLAN §5.2) — no flux limiters,
  no nonlinear terms, ever.
