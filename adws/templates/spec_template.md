# Dispatch-spec template (copy, fill {braces}, delete guidance lines)

Structure extracted from the five specs that ran clean through the factory on
2026-08-25/26 (ADW hardening, fanout/probe, Mission Control, two audits).
Builders interpret the spec flexibly; tools/pipeline_verify.py and the gates
check it exactly — so every requirement that matters MUST appear as a
machine-checkable acceptance criterion.

---

{One-line title: what to build and why it exists}

{2-3 sentences of context: what this is part of, what "done" enables. If a
verifier will run afterwards, say so — workers aim better when told the
checks are deterministic.}

Repo: /home/mbessalle/water-innovation-project (work in this checkout).
Python: .venv/bin/python. NO new dependencies. {other global constraints}

Touch ONLY: {allowed paths, explicit}. Never modify: {forbidden paths — at
minimum src/brineguard (unless the task IS numerics — then require full
pytest), docs/, runs/, FREEZE.md}.

Acceptance criteria (each independently machine-checkable; the verifier
greps these IDs, so keep the AC<n> markers):
- AC1: {observable property + how it will be checked (file exists, endpoint
  returns keys, test asserts X)}
- AC2: {...}
- AC{n-1}: tests in {tests/test_x.py} covering {the new behavior}; the ENTIRE
  suite stays green: run `.venv/bin/python -m pytest -q` before reporting and
  include its tail in your completion message.
- AC{n}: write the envelope to {adw_data/<task>/envelope.json} exactly as
  {"status": "succeeded", "summary": "<one paragraph>", "changed_files":
  [<paths>], "correlation": {"dispatch_id": "<from your task's dispatch
  context>", "attempt": 1}} — status "failed" with an honest summary if you
  could not finish. The correlation block is required so the verifier can
  attest each envelope to its dispatch.

{Optional: design taste in one line — aesthetics, size budgets.}

Report completion per your dispatch preamble (worker_done) with: files
changed, gate/test tails, envelope path.

---

Authoring rules for the orchestrator:
- Every "must" in prose needs a matching AC, or it will not be verified.
- Scope limits are ACs of omission — name forbidden paths explicitly.
- One task = one worker = one envelope. Split independent work into separate
  dispatches so the DAG can parallelize and failures stay local.
