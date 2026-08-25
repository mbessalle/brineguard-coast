# Evidence Index — canonical provenance map

Single source of truth mapping every preregistered claim (docs/CLAIMS.md) to
its exact artifact, sha256, generating command, and git lineage. The frozen
bundle lives in `evidence/2026-08-25/` and is bound by `evidence/manifest.json`.

## Environment (from run manifest `tool_versions`)

| Package | Version |
|---------|---------|
| python  | 3.14.4  |
| numpy   | 2.5.2   |
| pyomo   | 6.10.1  |
| scipy   | 1.18.1  |

## Git commit lineage

| Commit  | Meaning                                                              |
|---------|----------------------------------------------------------------------|
| `6e67577` | Declare Phase 5 evidence freeze (writes FREEZE.md header)           |
| `d28e584` | Audit correction: ensemble C cost-capped at cheaper B's nominal energy |
| `609b5b3` | Phase 5 T2: frozen evidence bundle generator (the rev recorded in `evidence/manifest.json`) |
| `aacd23c` | Commit frozen evidence bundle 2026-08-25                            |

### Why FREEZE.md says `41ffc83` but the manifest says `609b5b3`

The FREEZE.md header declares "Frozen at git `41ffc83`", while
`evidence/manifest.json` records `git_revision: 609b5b3`. This is expected and
harmless: the freeze text was drafted *before the freeze commit itself
existed*, so it captured the then-current HEAD (`41ffc83`, Phase 4 T4). The
bundle was actually generated later — after the audit correction (`d28e584`)
and the generator landed (`609b5b3`) — so the generator stamped its own HEAD
(`609b5b3`) into the manifest. Both statements are true at their respective
moments; `609b5b3` is the rev that *produced* the artifacts, `41ffc83` is the
rev the freeze *declaration* was written against.

## Generating commands

The whole bundle is produced by one command, which invokes the three section
runners below:

```sh
.venv/bin/python -m brineguard make-evidence      # == `make evidence`
```

Per section (as recorded in the enriched manifest `commands` field):

```sh
# benchmark
.venv/bin/python -m brineguard run-benchmark \
  -c configs/phase3.yaml -c configs/phase3_tidal.yaml -c configs/hybrid_redsea_full.yaml \
  --run-id benchmark --output-root evidence/2026-08-25

# ensemble (20 members, seed 20260825)
.venv/bin/python -m brineguard run-ensemble \
  -c configs/phase3_tidal.yaml --members 20 --seed 20260825 \
  --run-id ensemble --output-root evidence/2026-08-25

# sensitivity (8 pareto points)
.venv/bin/python -m brineguard run-sensitivity \
  -c configs/phase3.yaml --n-points 8 \
  --run-id sensitivity --output-root evidence/2026-08-25
```

## Claim → artifact map

Artifact paths are repo-root-relative. sha256 values are copied verbatim from
`evidence/manifest.json` (`artifact_sha256s`).

### C1 — Headline benefit (synthetic benchmark)

- **Artifacts:** `evidence/2026-08-25/benchmark/comparison.json` (cells
  `phase3/flex4`, `phase3_tidal/flex4`), `evidence/2026-08-25/benchmark/comparison.csv`
- **sha256:**
  - `comparison.json` → `8d13c5803a0025adf4baa27095e921556e105c84053f8e9f1f0ad4c165b18a81`
  - `comparison.csv` → `a9b80b583919a7e1dfae5f4217693b5efb3c4ba6f0490ecf6be9519d72a98ac7`
- **Command:** benchmark runner (above)
- **Lineage:** produced at `609b5b3`, committed at `aacd23c`

### C2 — Benefit scales with operational flexibility

- **Artifacts:** benchmark cells `phase3/flex1`, `phase3/flex2`
  (`evidence/2026-08-25/benchmark/comparison.json`);
  `evidence/2026-08-25/sensitivity/sensitivity.json` (`sensitivity_sweep`)
- **sha256:**
  - `benchmark/comparison.json` → `8d13c5803a0025adf4baa27095e921556e105c84053f8e9f1f0ad4c165b18a81`
  - `sensitivity/sensitivity.json` → `cca449dc07f4040338d9dab34d539d2c866482d4e6dd54a2af21642bc76618ac`
- **Command:** benchmark + sensitivity runners (above)
- **Lineage:** produced at `609b5b3`, committed at `aacd23c`

### C3 — Robustness to forecast error (matched cost)

- **Artifacts:** `evidence/2026-08-25/ensemble/ensemble.json`
- **sha256:** `6a74289b2bf311914bf23fad00f26d5c3d77a2604913afe5bd743c999e986e01`
- **Command:** ensemble runner (above); regenerated after the `d28e584`
  cost-cap correction (FREEZE.md addendum documents the change)
- **Lineage:** produced at `609b5b3` (post-`d28e584`), committed at `aacd23c`

### C4 — Cost–protection trade-off is published, not hidden

- **Artifacts:** `evidence/2026-08-25/sensitivity/sensitivity.json`
  (`pareto_frontier`); `evidence/2026-08-25/sensitivity/figures/pareto_frontier.png`
- **sha256:**
  - `sensitivity/sensitivity.json` → `cca449dc07f4040338d9dab34d539d2c866482d4e6dd54a2af21642bc76618ac`
  - `sensitivity/figures/pareto_frontier.png` → `844b1160680d8c73c33ec2fccba7d2a0dcb46877860c01d98aac42f064f3a470`
- **Command:** sensitivity runner (above)
- **Lineage:** produced at `609b5b3`, committed at `aacd23c`

### C5 — Real-coastline result and the screening principle (NULL RESULT)

- **Artifacts:** benchmark cells `hybrid_redsea_full/*`
  (`evidence/2026-08-25/benchmark/comparison.json`); diagnosis scripts in the
  session log (deterministic, 2026-08-26); dose-spread numbers reproducible
  from `build_kernel` + receptor areas
- **sha256:** `benchmark/comparison.json` →
  `8d13c5803a0025adf4baa27095e921556e105c84053f8e9f1f0ad4c165b18a81`
- **Command:** benchmark runner (above)
- **Lineage:** produced at `609b5b3`, committed at `aacd23c`

## Verification statement

`make verify-evidence` (i.e. `.venv/bin/python -m brineguard make-evidence
--verify`) re-runs generation into a throwaway temp dir and asserts every
coordination_benefit, exposure percentile, and pareto point matches within
rtol 1e-9 — **PASS**. The same gate is exercised automatically by
`tests/test_evidence.py::test_verify_evidence_passes_on_mini_bundle`.
