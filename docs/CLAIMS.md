# BrineGuard Coast — Claim Table (preregistered wording)

Every quantitative claim the submission makes, its exact conditions, and its
evidence artifact. Wording here is canonical: the deck, video, portal answers,
and dashboard must not exceed it. Null and negative results are claims too.
Frozen evidence: `evidence/2026-08-25/` (sha256 manifest; `make verify-evidence`
reproduces every number). Independent adversarial audit (GPT-5.6 Sol,
2026-08-25) recomputed the headline ratios from raw fields and verified the
physics; its corrections are incorporated below.

## C1 — Headline benefit (synthetic benchmark)

**Claim:** On the synthetic three-plant benchmark with network flexibility
(shared storage, full turndown range), coordinated dispatch reduces
salinity-exposure proxy by **18.6–20.3% (steady currents) and 19.4–20.9%
(tidal currents)** relative to independently optimized plants, **at no greater
energy cost** (in the steady case the coordinated schedule is strictly
cheaper — it dominates on both axes).
**Conditions:** flex4 scenario; per-plant dose-coefficient spread 3.3×;
exposure evaluated by direct transport re-simulation, never the optimizer's
own proxy. **Evidence:** `evidence/2026-08-25/benchmark/comparison.json`,
cells `phase3/flex4`, `phase3_tidal/flex4`.

## C2 — Benefit scales with operational flexibility

**Claim:** Benefit is 0.0% with no flexibility (all strategies provably
identical — harness fairness check), 1.2–1.5% with ±10% turndown, and
18.6–20.9% with network flexibility. Sensitivity: 0.6%→5.3% across turndown
5%→20%; 17.9%→19.3% across storage ×0.5→×2 (benefit is structural, not a
storage artifact); 24.0%→14.1% across dispersion ×0.5→×2 (less natural mixing
→ more coordination value).
**Evidence:** benchmark cells flex1/flex2; `sensitivity/sensitivity.json`.

## C3 — Robustness to forecast error (matched cost)

**Claim:** With schedules optimized on the nominal forecast only and the
coordinated schedule **cost-capped at the cheaper independent baseline's
energy spend (cap binding)**, benefit is positive on **all 20 ensemble
members** (19 truly held-out): 14.5–26.0% (capacity rule), 16.1–27.9% (cost
rule). Coordination's p95 exposure sits below the cost-rule baseline's p5;
against the capacity-rule baseline the intervals touch within 0.2%.
**Evidence:** `evidence/2026-08-25/ensemble/ensemble.json` (regenerated after
the audit's cost-cap correction; FREEZE.md addendum documents the change).

## C4 — Cost–protection trade-off is published, not hidden

**Claim:** The full Pareto frontier is reported: from 28,860 to 32,036 energy
cost units, exposure falls 11,538 → 8,389 (a +10.7% budget buys −27%
exposure). No single penalty weight backs any headline claim.
**Evidence:** `sensitivity/sensitivity.json` pareto_frontier; every point
feasible, monotone.

## C5 — Real-coastline result and the screening principle (NULL RESULT)

**Claim:** On real GEBCO Red Sea bathymetry with representative-scale assumed
plants (100k–300k m³/day class) and assumed tidal currents, coordination
benefit is **≈0 (−0.8% to +0.7%)**. Diagnosis (2026-08-26, deterministic
scripts): benefit requires *spatial asymmetry* in per-plant environmental
dose coefficients and *feasible reallocation range*. A linear-regime bound
computed ex ante from the kernel — reallocating production cleanest-first
within plant limits — **predicts both outcomes**: 16.3% bound where 19–21%
was measured (synthetic, 3.3× dose spread), 4.3% bound where ≈0 was measured
(hybrid geometry, 1.5× spread + 40%-of-max turndown floors).
**Framing rule:** this is reported as a screening capability — the kernel
predicts, before any optimization, whether a corridor's geometry and plant
flexibility make coordination worthwhile — never hidden, never spun as
site-specific failure or success. flex2 at this plant scale is infeasible
under the harness's turndown transform (recorded limitation).
**Evidence:** benchmark cells `hybrid_redsea_full/*`; diagnosis scripts in
session log; dose-spread numbers reproducible from `build_kernel` +
receptor areas.

## C6 — What is NOT claimed

No ecological/biological outcome (salinity-exposure proxy only, thresholds
are configurable screening values); no site-specific accuracy (hybrid domain
= real bathymetry + assumed plants + assumed currents); no operational
deployment (TRL 1–3 computational proof of concept); no autonomous plant
control (shadow/advisory mode only); benefit magnitudes are properties of
the benchmark configurations, conditional per C5's screening principle.

## Verification chain (any claim above)

1. `.venv/bin/python -m pytest -q` — 82 tests incl. negative tests of the auditors.
2. `make verify-evidence` — regenerates every metric, fails on any mismatch.
3. Kernel ↔ independent FD solver agreement gates pass on every domain incl.
   the real coastline; every schedule re-simulated through the direct solver;
   water-balance audit zero-violation gate.
4. Adversarial audit trail: `adw_data/gpiw_gap_report.md` (submission fit),
   audit findings and fixes in git history (`d28e584`, FREEZE addendum).
