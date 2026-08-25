# Playbook format (LLM-interpreted pseudo-code, first-class artifact)

INTERPRETATION CONTRACT: a playbook is exactly interpretable, flexibly
executable. The executing agent may adapt the HOW (exact argv details that
drifted, orderings, diagnostic depth) but never the WHAT (the goal of each
step), never the VERIFY step, and never the ESCALATE boundary. A playbook
always ends by handing control back to deterministic code — it recovers and
routes, it does not decide correctness.

Boundary rule (also in CLAUDE.md): code decides and verifies (gates,
preflight, verdict flow, ledger); playbooks carry procedures whose
environment drifts faster than code maintenance (recovery, triage,
escalation); templates carry intent across DAG edges (specs, role prompts).

Every playbook has exactly these sections:

## TRIGGER
The exact observable condition (error string, event type, gate output) that
activates this playbook. If the observed condition only resembles the
trigger, do not run the playbook — diagnose first.

## PRECONDITIONS
What must be true before step 1 (which tool failed, what state files exist).

## PROCEDURE
Numbered steps. Each step is one of:
- RUN: an exact command (copy-paste ready). Mark drift-prone fragments with
  {braces} and say how to re-derive them.
- DECIDE: a branch with explicit, observable criteria for each arm.
- ADAPT: a bounded improvisation zone — state what may vary and what must not.

## VERIFY
The deterministic check (command + expected output/exit code) that proves the
recovery worked. Never conclude success without running it.

## ESCALATE
The conditions under which the agent stops and surfaces to the user instead
of continuing (attempts exhausted, destructive action required, contradiction
with a frozen artifact). Escalation is a success mode, not a failure.

Index: dispatch_recovery.md · escalation_triage.md
Templates live in adws/templates/ (spec_template.md).
