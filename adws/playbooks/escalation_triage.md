# Playbook: escalation / question triage (the agent-hook, as pseudo-code)

TRIGGER: the wait loop prints an `escalation` or `question` message from a
dispatched worker (orca_dispatch wait output line `[wait] escalation ...` or
`[wait] question ...`).

PRECONDITIONS: the message id and dispatch id are visible in the wait output
and ledger; the worker is still alive (do not release it).

PROCEDURE:
1. DECIDE — classify the message body into exactly one:
   a. MISSING-INFO: the worker lacks facts derivable from the repo/environment
      (where is X, which config value, what does the contract say).
   b. ENVIRONMENT-BLOCKED: the worker hit a permission wall, missing binary,
      missing key, or locked resource.
   c. STRUCTURAL: the spec is contradictory, an acceptance criterion is
      unsatisfiable, or the change collides with an architectural invariant
      (kernel linearity, run-artifact contract, frozen evidence).
2. For MISSING-INFO — spend scout tokens before Tier-1 tokens:
   RUN `python3 tools/orca_dispatch.py run --route scout --wait --timeout 300 --spec "READ-ONLY recon, no edits. Question from a builder working on {task_id}: {verbatim question}. Find the answer in /home/mbessalle/water-innovation-project (grep/read only). Reply with: the answer, the file:line evidence, and nothing else."`
   Then relay: RUN `python3 tools/orca_dispatch.py send --dispatch {worker_dispatch_id} --body "{scout answer, plus its file:line evidence}"`.
   ADAPT: skip the scout and answer directly when the answer is already in
   the orchestrator's context — the scout exists to save tokens, not to add
   a hop for its own sake.
3. For ENVIRONMENT-BLOCKED: fix the environment yourself IF it is
   orchestrator-owned (keys via .env, allowlists, worktree selectors — see
   dispatch_recovery.md), then `send` the go-ahead. NEVER instruct the worker
   to bypass a permission wall (that is permission laundering); if the wall
   is the user's, ESCALATE.
4. For STRUCTURAL: do not improvise an answer to the worker. Stop the
   phase: reply that the task is paused, then re-plan at Tier 1 (amend the
   spec, re-dispatch) or surface to the user if the contradiction touches
   frozen claims/evidence.

VERIFY: the worker acknowledges (next heartbeat/output) and resumes, or the
task is formally paused via task-update. The question message is acked in the
wait loop — never leave it unacked to replay.

ESCALATE: same question repeats after a scout-grounded answer (the worker is
looping — treat as retry-ladder failure), or classification is (c) touching
FREEZE.md/docs/CLAIMS.md, or any answer would require granting the worker
permissions it was denied.
