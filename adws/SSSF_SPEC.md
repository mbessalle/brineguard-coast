You are an expert Agentic Engineer. Configure this repository to follow the "Super Simple Software Factory" (SSSF) architecture, establishing a tiered model stack and enforcing an "Agents + Code > Agents Alone" pattern to maximize compute efficiency while minimizing token cost.

---

### 1. Establish the Tiered Model Stack & Routing Policy
Configure the orchestrator configuration (`sssf.config.yaml` or orchestrator settings) to route tasks dynamically across three model tiers rather than defaulting everything to expensive frontier models:

- **Tier 1: SOTA / Reasoning Tier** (e.g., `claude-opus`, `kimi-k3`, `gpt-5-reasoner`):
  - *Assigned Roles:* Architecture Planner (`planner`), Critical Spec Reviewer (`reviewer`).
  - *Usage:* High-depth reasoning, planning, breaking down complex requirements, final semantic verification.
- **Tier 2: Workhorse Tier** (e.g., `gemini-flash`, `gpt-mini`, `claude-sonnet`):
  - *Assigned Roles:* Builder/Coder (`builder`), Scout/Recon (`scout`), Documentation Writer (`documenter`).
  - *Usage:* Code generation against a strict plan, file edits, code search/indexing, diff summarization.
- **Tier 3: Lightweight / Deterministic Layer** (Local code execution & free tools):
  - *Assigned Roles:* Quality Gates, Testing, Typecheck, Linting, Git operations.
  - *Rule:* Zero token usage. All deterministic checks must run locally in bash/Python.

---

### 2. Implement Deterministic Quality Gates (Code Before LLM)
Do NOT waste LLM tokens verifying syntax, formats, or basic execution. Implement local Python/bash gate checks between workflow phases:

1. **Artifact Verification:** Check that required output files exist and are non-empty (`artifacts_exist`, `files_non_empty`).
2. **Schema & JSON Validation:** Validate structured JSON envelope handoffs before passing them to the next agent (`json_parse`).
3. **Deterministic Quality Suite (`code(quality)`):**
   - Run type checks (`tsc`, `pyright`, `mypy`), formatters/linters (`biome`, `ruff`, `eslint`), and test runners (`pytest`, `vitest`, `bun test`).
4. **Bounded Retry Loop:**
   - If tests/gates fail, pass only the exact error stderr/stdout back to the **Workhorse Builder** for a bounded fix attempt (max 2–3 retries).
   - Only escalate to the **SOTA Planner** if structural changes are needed.

---

### 3. Standardize Context Handoffs via Artifacts (Not Raw Chat History)
Minimize context window bloat by passing state via filesystem envelopes rather than monolithic conversation histories:

- **Handoff Artifacts Directory:** Store session state in `adw_data/sessions/<session_id>/context_handoff/`.
- **Phase Output Envelopes:**
  - `planner` outputs `plan.md` + JSON metadata (`status`, `summary`, `changed_files`).
  - `builder` consumes `plan.md`, implements changes, and outputs `envelope.json` with commit messages.
  - `tester` runs deterministic bash tests and outputs test logs.
  - `reviewer` verifies only the Git diff against `plan.md`.

---

### 4. Create Standard Starter Workflows (ADWs)
Scaffold the following reusable, observable AI Developer Workflows:
1. `adw_scout`: Fast recon on codebase/architecture using Workhorse tier (read-only, no state mutation).
2. `adw_plan_build_test`: Planner (SOTA) -> Builder (Workhorse) -> Test/Gate (Code) -> Git commit.
3. `adw_simple_sdlc`: End-to-end SDLC: Request -> Plan (SOTA) -> Build (Workhorse) -> Test (Deterministic) -> Review (SOTA) -> Document (Workhorse) -> Commit.

---

### Execution Target
Generate the required config files (`sssf.config.yaml`), runner harness scripts, and gate verification helpers in this repo, ensuring all agent harness definitions are specialized, observable, and strictly separated between **Engineer**, **Agent**, and **Code**.
