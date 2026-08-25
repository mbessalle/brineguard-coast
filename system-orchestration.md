Here is the structured specification and architectural information extracted from the video to feed directly into your orchestrator agent’s memory, skills, and tool definitions:

---

# Multi-Agent Harness Architecture & Memory Context

## 1. Core Operating Principles
* **Combine Compute, Don't Select (AND over OR):** Rather than choosing a single model, combine complementary models across tiers to achieve higher accuracy, speed, and cost efficiency.
* **The Trade-Off Triangle:** Optimize continuously across three vectors:
  1. **Performance** (Task correctness and depth)
  2. **Speed / Throughput** (Tokens per second / Latency)
  3. **Cost** (Input/output token unit economics)
* **Key Metric:** Optimize for **Effective Agent Hour per Token Cost**.
* **Model Anonymization / Identity Masking:** **Never** expose the actual model names (e.g., GPT, Claude, DeepSeek) to peer agents in multi-agent prompts. Use abstract role aliases (e.g., `Architect/Rune`, `Builder-1/Flux`, `Builder-2/Drift`) to avoid bias, artificial sycophancy, or adversarial model behavior.
* **Evolutionary Goal:** Transition from **In-Loop Agentic Coding** (human babysitting prompts) to **Out-Loop Agentic Coding / Software Factories** (code + autonomous multi-agent pipelines executing end-to-end).

---

## 2. Model Tier Allocation Strategy

| Tier | Role | Typical Models | Responsibilities in Harness |
| :--- | :--- | :--- | :--- |
| **SOTA (S / S+ Tier)** | **Architect / Lead Orchestrator** | Claude Fable 5, Opus 5, GPT-5.6 Sol | High-level synthesis, task decomposition, dependency graphing (DAG), architectural decisions, final integration/validation. |
| **Workhorse (A / B Tier)** | **Builders / Specialists** | Gemini 3.7 Flash, DeepSeek V4 Pro, GLM-5.3 | High-speed implementation, parallel code generation, initial draft proposals, unit test execution. |
| **Lightweight (C / D Tier)** | **Local / Utility Agents** | Qwen 3.8-27B, Nemotron 3.5, Local OSS | Cheap sub-tasks, local syntax checking, linting, single-file audits. |

---

## 3. Core Multi-Agent Interaction Skills / Tools to Implement

### Tool 1: `/fh-opinion` (Read-Only Divergence)
* **Goal:** Solicit unconstrained, diverse opinions from multiple models on a specific technical question or design choice.
* **Execution Flow:**
  1. Fan out the prompt concurrently to all active models across tiers.
  2. Set execution mode to **Read-Only** (no file edits).
  3. Collect individual analyses, cost metrics, and recommendations.
  4. Aggregate opinions side-by-side without forcing a synthesis.

### Tool 2: `/fh-debate` (Multi-Round Adversarial Consensus)
* **Goal:** Stress-test architectural decisions and critical claims through multi-round structured debate.
* **Execution Flow:**
  * **Round 1 (Opening Positions):** Each agent reads the source document/claim and outputs an independent position with justification.
  * **Round 2 (Cross-Examination / Rebuttals):** Each agent is provided the anonymized positions of all other agents and must refute weaknesses or refine its own stance.
  * **Round 3 (Closing Statements & Settlement):** Agents issue their final verdict (e.g., *Accept*, *Reject*, *Pilot/Evaluate*), establishing areas of consensus and documented dissents.

### Tool 3: `/fh-collaborate` (DAG-Based Team Execution)
* **Goal:** Execute end-to-end coding and engineering tasks using parallel builder agents supervised by an architect agent.
* **Execution Flow:**
  1. **Proposal Phase:** All agents generate an independent end-state proposal and task outline.
  2. **Architect Synthesis (Plan/DAG):** SOTA Architect synthesizes proposals into a structured task dependency graph:
     * Task IDs (`T1`, `T2`, `T3`, ...)
     * Explicit dependencies (`depends_on: [T1]`)
     * Assigned owner (`Builder-1`, `Builder-2`)
     * Collision prevention rule: **Single writer per file/task at any given time**.
  3. **Execution Phase:** Builders execute parallel tasks as dependencies resolve, writing code and running ephemeral tests.
  4. **Integration & Auto-Validation:** Architect verifies integration against test harness (gate must exit with code `0` and passing assertions) and produces final handoff documentation.

---

## 4. Supporting Tool Definitions & Harness Commands

* **`/fh-auto-validate`**: Writes test gates and validation scripts first; forces builders to iterate until tests pass (`exit 0`).
* **`/fh-system-prompt`**: Dynamically prepends/appends system prompts per slot to enforce format rules, context constraints, or personality tuning.
* **`/fh-reset`**: Clears context memory across all active slots to prevent token bloat and memory cross-contamination.
* **`TIL-Done List Tracker`**: Maintain an explicit status board (`TODO`, `IN_PROGRESS`, `BLOCKED`, `DONE`) visible to all agents during collaboration workflows.
