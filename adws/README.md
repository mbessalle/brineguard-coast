# adws/ — AI Developer Workflows (SSSF)

Source spec: `adws/SSSF_SPEC.md`. Configuration: `sssf.config.yaml`.

## Tier Table (verified routes, live 2026-08-25 via `tools/probe.py`)

| Tier | Roles | Backend | Model |
|------|-------|---------|-------|
| 1 SOTA | planner, reviewer | session (orchestrating Claude Code) | claude-fable-5 |
| 1b independent | reviewer_independent | openrouter-api | moonshotai/kimi-k3 |
| 2 Workhorse | builder | pi-openrouter | deepseek/deepseek-v4-pro |
| 2 Workhorse | scout | pi-openrouter | deepseek/deepseek-v4-flash |
| 2 Workhorse | documenter | openrouter-api | openai/gpt-5-mini |
| 3 Deterministic | quality_gate, test_runner, artifact_verifier, schema_verifier | local | n/a (zero-token) |

## Workflows

### adw_scout — fast, read-only recon
```bash
.venv/bin/python adws/adw_scout.py --topic "how does dispatch work?" [--dry-run]
```

### adw_plan_build_test — Planner -> Builder -> Gate -> Commit
```bash
.venv/bin/python adws/adw_plan_build_test.py --request "add X" [--dry-run] [--no-commit]
```

### adw_simple_sdlc — Full SDLC: Plan -> Build -> Test -> Review -> Document -> Commit
```bash
.venv/bin/python adws/adw_simple_sdlc.py --request "add X" [--dry-run] [--no-commit]
```

### tools/orca_dispatch.py — Orca supervised worker dispatch
```bash
python3 tools/orca_dispatch.py run --spec "build X" --route builder [--wait] [--dry-run]
python3 tools/orca_dispatch.py status
python3 tools/orca_dispatch.py send --dispatch ctx_abc123 --body "proceed"
```

## Envelope Contract

All phases communicate via filesystem envelopes in
`adw_data/sessions/<session_id>/context_handoff/`. Every envelope is a JSON
object with at minimum `{"status": "...", "summary": "...", "changed_files": [...]}`.
Phase-specific envelopes add extra keys (`commit_message`, `verdict`, etc.).

## Engineer / Agent / Code Separation

- **Engineer** (human or coordinator): sets policy in `sssf.config.yaml` and
  `adws/prompts/`, chooses which workflow to run, reviews escalations.
- **Agent** (LLM): planner, builder, reviewer, documenter, scout — invoked
  headless via `adw_common.run_route()` with a prompt template and a route from
  `sssf.config.yaml`.
- **Code** (deterministic, zero-token): `adws/gates.py` for quality gates,
  `adw_common.py` for session/artifact plumbing, `tools/orca_dispatch.py` for
  supervised worker dispatch. Never calls an LLM.

## Adding or Changing a Route

Edit `sssf.config.yaml` — no code changes required:
1. Add/update the backend in `backends` (argv template).
2. Add/update the route in `routes` (backend + model + optional cost/role_prompt).
3. For new roles, add a tier entry and a routing.default_tier_by_role entry.
4. Verify with `python3 tools/probe.py` before trusting the route.