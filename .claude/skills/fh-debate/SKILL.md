---
name: fh-debate
description: Multi-round adversarial consensus — stress-test an architectural decision or critical claim through a 3-round structured debate between anonymized model routes (positions, rebuttals, verdicts). Use before hard-to-reverse decisions.
---

# /fh-debate — Multi-Round Adversarial Consensus

Stress-test a decision/claim via structured debate (system-orchestration.md
Tool 2). Agents are only ever shown each other's **anonymized aliases**.

## Execution

**Round 1 — Opening positions.** Fan the source document/claim out read-only:
`python3 tools/fanout.py --prompt-file <claim.md> --routes <3+ routes> --out <dir>/r1`
Prompt template: "Read the following and output an independent position with
justification: ACCEPT, REJECT, or PILOT, and why."

**Round 2 — Cross-examination.** Build one prompt per route containing the
claim plus ALL round-1 positions labeled only by alias (the engine's saved
files are already alias-labeled). Instruct: "Refute weaknesses in the other
positions or refine your own stance." Fan out again to the same routes:
`python3 tools/fanout.py --prompt-file <dir>/r2_prompt.md --routes <same> --out <dir>/r2`

**Round 3 — Closing & settlement.** Same mechanism; instruct each agent to
issue a final verdict (Accept / Reject / Pilot-Evaluate) in one line plus a
short justification.

**Settlement (Tier 1, you).** Tabulate verdicts by alias, state the consensus
and every documented dissent. Consensus does not overrule your judgment — but
record when you override it and why.

## Rules

- 3 routes minimum for a meaningful debate; include at least one non-default
  provider family.
- Never leak real model names into any round's prompt.
- Persist all rounds under the chosen out dir for auditability.
