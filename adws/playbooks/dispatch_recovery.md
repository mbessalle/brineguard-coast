# Playbook: dispatch recovery (Orca worker loop failures)

Six recovery patterns, each proven live in this project. Sections are
numbered; tools print "see adws/playbooks/dispatch_recovery.md §n" at the
matching failure exit.

## §1 waiter_exists

TRIGGER: any orca call returns error code/message containing "waiter" and
"exists" ("Run ... already has an active actionable waiter").
PRECONDITIONS: you (or a crashed predecessor) started a `check --wait`.
PROCEDURE:
1. RUN `python3 tools/orca_dispatch.py wait --timeout <n>` — its loop already
   degrades to 10s plain-check polling on waiter_exists (proven 2026-08-25,
   builder-1 completion was received in poll mode). Prefer this over manual
   commands.
2. DECIDE: if polling also errors, an orphaned waiter from a dead process
   holds the slot. RUN `orca orchestration check --types worker_done,escalation,question --json`
   (no --wait) to consume the pending Delivery directly; ack via the next
   check `--ack {delivery_id}`.
3. ADAPT: never kill terminals to clear a waiter; waiters die with their
   process, orphaned ones expire.
VERIFY: a subsequent `check` returns ok:true (empty batch is fine).
ESCALATE: waiter persists across 10+ minutes AND deliveries are visibly
queuing (peek shows messages) — surface to user before killing anything.

## §2 selector_not_found (worker-start / terminal ops)

TRIGGER: orca returns {'code': 'selector_not_found'}.
PRECONDITIONS: command used a relative selector ("current", "active") from a
terminal not bound to a worktree Orca resolves.
PROCEDURE:
1. RUN `orca worktree list --json` and find the row whose path is the repo
   (/home/mbessalle/water-innovation-project). The selector is the exact
   `id` field, format {uuid}::{path}.
2. RUN the failed command again with `--worktree "{that selector}"` — for
   dispatches: `python3 tools/orca_dispatch.py run ... --worktree "{selector}"`.
   (Proven: fixes both the codex worker-start 2026-08-25 and the earlier
   phase-3 incident.)
VERIFY: command returns ok:true and the ledger row records the terminal.
ESCALATE: worktree list has no row for the repo — the workspace binding is
gone; that is an Orca-app state problem for the user.

## §3 silent worker_done (worker finished, no completion event)

TRIGGER: worker terminal is TUI-idle, expected outputs exist on disk, but no
worker_done arrives across two full wait windows.
PRECONDITIONS: task status still "dispatched" in `orca orchestration task-list --json`.
PROCEDURE:
1. RUN `orca terminal read --terminal {handle} --json` — confirm idle prompt,
   no error screen (distinguish from §5 crash).
2. RUN the envelope gate: `python3 adws/gates.py json {envelope_path}` — must
   pass, including verdict rules.
3. RUN the deliverable gates the spec named (pytest, quality) yourself.
4. DECIDE: all green → the work is real, only the signal was lost (known OMP
   failure mode, hit twice; see the omp-pi skill). RUN
   `orca orchestration task-update --task {task_id} --status completed --json`.
   Anything red → treat as §5, do not mark completed.
VERIFY: task-list shows the task completed; ledger updated.
ESCALATE: envelope or gates fail — the worker died mid-work; report state to
user before re-dispatching (the worktree may hold partial edits).

## §4 CLI blocked by its own updater (codex update prompt etc.)

TRIGGER: worker CLI refuses to start, output demands an update/interactive
confirmation (e.g. codex-update-prompt).
PROCEDURE:
1. RUN the updater non-interactively (codex: `codex update`; pi: `npm i -g
   @mariozechner/pi-coding-agent`). Record the new version in the reply.
2. RUN model preflight for the route (`python3 tools/model_preflight.py check
   {provider} {model}`) — an update can change the catalog (this is how the
   gpt-5.6-sol gap would have been caught).
3. Retry the original dispatch.
VERIFY: worker reaches ready state; preflight OK.
ESCALATE: updater requires login/interaction — hand the exact command to the
user (`! <command>` in the prompt).

## §5 terminal-wait timeout / worker crash at startup

TRIGGER: `terminal wait --for tui-idle` times out, or terminal exits.
PROCEDURE:
1. RUN `orca terminal read --terminal {handle} --json`; read the tail.
2. DECIDE by content: auth/key error → fix env (see launch script's key
   check), re-create terminal. Model warning ("Could not restore model") →
   STOP: the runtime fell back to another model; never dispatch onto a
   fallback (this is the gpt-5.5 incident); fix the route per preflight.
   Empty/cold → one more 60s wait (cold start), then re-create.
3. ADAPT: reuse `--terminal {handle}` of a healthy idle worker instead of
   re-creating, when one exists.
VERIFY: tui-idle reached AND no fallback warning in the buffer.
ESCALATE: two consecutive create+wait failures for the same route.

## §6 handoff-verify mismatch (stored spec != sent spec)

TRIGGER: dispatch tooling or pipeline_verify reports the Orca-stored task
spec hash differs from the sent spec file hash.
PROCEDURE:
1. Do NOT dispatch or let the worker proceed — a worker acting on a corrupted
   task produces plausible wrong work.
2. RUN task-create again from the spec file; re-verify the hash; dispatch the
   NEW task id; abandon the corrupted task (task-update failed with reason).
VERIFY: pipeline_verify stage-1 prompt_delivered PASS on the new task.
ESCALATE: mismatch recurs — encoding/size issue in the transport; report with
both hashes and lengths.
