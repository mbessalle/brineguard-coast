# Playbook: warm-fix loop (verification feedback to a live worker)

Adopted from disler/the-verifier-agent: when verification fails after
worker_done, a still-alive worker fixes faster and cheaper in-session than a
cold re-dispatch (keeps its context window; no terminal/model cold start).

TRIGGER: any deterministic gate fails on a completed dispatch — pipeline
verifier FAIL row, `gates.py json|diffclaims|protected|quality` nonzero, or
the orchestrator's own pytest run — while the worker's terminal still exists.

PRECONDITIONS: dispatch_id known (ledger); worker terminal alive
(`orca terminal read --terminal {handle} --json` succeeds, no error screen).

PROCEDURE:
1. RUN the failing gate once more and capture its RAW output (never a
   summary — retry_input policy).
2. DECIDE: is the failure inside the worker's dispatched scope?
   - Yes → step 3. No (my machinery, environment, or another task's files) →
     fix the environment side yourself; this playbook does not apply.
3. RUN `python3 tools/orca_dispatch.py send --dispatch {dispatch_id} --body
   "VERIFICATION FAILED — fix and report worker_done again. Raw gate output:
   {verbatim output}. Constraints unchanged: same spec, same scope limits,
   full suite green before reporting."`
4. RUN `python3 tools/orca_dispatch.py wait --timeout 520` for the corrected
   worker_done.
5. ADAPT: at most 2 warm-fix rounds. Count them. On the 3rd failure, stop —
   fall back to the retry ladder (escalation rung or re-plan), per
   sssf.config.yaml retry_policy. Never loop warm fixes unbounded.

VERIFY: the originally failing gate now passes, then the FULL check set for
the run (pipeline verifier stage 2 when a manifest exists).

ESCALATE: two warm-fix rounds exhausted; or the failure implicates protected
files or frozen evidence; or the worker's fix changed files outside its spec
scope (diff_matches_claims will catch this — treat as scope violation, not a
fix).
