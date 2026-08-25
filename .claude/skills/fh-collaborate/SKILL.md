---
name: fh-collaborate
description: DAG-based team execution — decompose an end-to-end engineering task into a dependency graph and execute it with parallel Orca-dispatched builders under Tier 1 supervision, single writer per file, gates as integration check. Use for multi-part implementation work.
---

# /fh-collaborate — DAG-Based Team Execution

End-to-end task execution with parallel builders supervised by the Architect
(system-orchestration.md Tool 3). Uses the existing Orca machinery — never the
internal Agent tool.

## Execution

1. **Proposal phase (optional, for contested designs):** run /fh-opinion on
   the end-state first; skip for well-specified tasks.
2. **Architect synthesis (you, Tier 1):** decompose into tasks `T1..TN` with
   explicit dependencies and owners. **Single writer per file at any time** —
   no two concurrent tasks may touch the same file. Keep chains ≤3-4 deep.
3. **Create the DAG in Orca** (statuses TODO/IN_PROGRESS/BLOCKED/DONE map to
   Orca's pending/dispatched/blocked/completed):
   ```
   orca orchestration run-create --objective "..." --json
   orca orchestration task-create --spec "<T1 spec>" --json
   orca orchestration task-create --spec "<T2 spec>" --deps '["<t1_id>"]' --json
   ```
4. **Dispatch ready tasks in parallel** via `python3 tools/orca_dispatch.py run
   --spec @<spec> --route builder [--wait]` (route per sssf.config.yaml;
   builder_escalation for gnarly tasks). `orca orchestration task-list --ready
   --json` is the status board — use it as external memory each wave.
5. **Integration & auto-validation (you + Tier 3):** after each wave, run
   `.venv/bin/python -m pytest -q` and `adws/gates.py quality` yourself — a
   wave is DONE only when gates exit 0. Then dispatch the next ready wave.
6. **Handoff:** final summary of tasks, owners, gate evidence, and commits.

## Rules

- Workers see aliases, not model names, in any shared context.
- Every dispatch needs Orca provenance (task + dispatch ids).
- Release every settled worker (`worker-release`) before the next wait.
