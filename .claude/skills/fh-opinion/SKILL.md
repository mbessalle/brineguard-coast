---
name: fh-opinion
description: Read-only divergence — fan one technical question out concurrently to multiple model routes, collect independent opinions with cost metrics, and present them side-by-side without forcing a synthesis. Use for design choices, technical questions, or claims that benefit from diverse model perspectives.
---

# /fh-opinion — Read-Only Divergence

Solicit unconstrained, diverse opinions from multiple models on one technical
question or design choice (system-orchestration.md Tool 1).

## Execution

1. Take the question from the arguments (or ask for it if absent).
2. Fan out concurrently via the deterministic engine:
   `python3 tools/fanout.py --prompt-file <q.md> --routes builder,scout,reviewer_independent,documenter [--out <dir>]`
   - Read-only is guaranteed by the engine (chat-only invocations, no tools).
   - Routes come from sssf.config.yaml; add/drop routes per question weight.
3. The engine labels each response with its **anonymized alias** from
   `anonymization.aliases` (never real model names in any content another
   agent will later see).
4. Present the opinions **side-by-side, unsynthesized**: one section per alias
   with its recommendation, plus the engine's per-route latency and cost
   figures. Add your own Tier 1 view only afterward and clearly marked.
5. If responses will feed a debate, keep the saved per-alias files for
   /fh-debate round 2.

## Rules

- Do not collapse disagreement into a consensus — divergence is the product.
- Report cost per route (the engine prints estimates from sssf.config.yaml
  pricing fields).
