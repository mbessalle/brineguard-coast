# BrineGuard Coast — Prototype Build Plan

**Status:** CANONICAL, final cross-check complete, 25 August 2026.
**Deadline:** 30 September 2026. **Target:** GPIW Track A computational proof of
concept, not an operational controller.

## 0. Provenance and final cross-check

This document went through four passes: independent drafts (Claude's `BUILD_PLAN_CLAUDE.md`,
Codex's `BUILD_PLAN_CODEX.md`), a first merge (Claude), a Gemini Deep Research pass on
the open library/data/prior-art questions (`DEEP_RESEARCH_BUILD_TOOLING.md`), and a
second, deep-research-informed merge (Codex's `BUILD_PLAN_CODEX_FINAL.md`). This is
Claude's final cross-check of that second merge — verifying its decision-gate
resolutions, checking it didn't quietly force a pick on the one genuinely open dispute,
and independently checking its new citations rather than trusting them. **Codex's
`BUILD_PLAN_CODEX_FINAL.md` is the backbone of what follows** — it was more complete
and more carefully reasoned than Claude's own second-pass draft on several specific
points (listed below), which this cross-check adopts rather than re-litigates. A small
number of gaps are patched back in.

**What the cross-check verified independently, not just accepted:**
- The FlexPWF citation (Oikonomou & Parvania, *IEEE Trans. Smart Grid* 11(6),
  pp. 4784–4794, 2020, DOI `10.1109/TSG.2020.3000173`) is real, and its actual abstract
  matches the description given — co-optimizing flexible desalination/pump/storage
  assets with power and water distribution systems. Correctly cited.
- The caution around `dw-data/desalination` is not just defensible-sounding, it's
  **exactly what the repo's own README says**: primarily FAO AQUASTAT country-level
  data, with the plant-capacity figures explicitly sourced from proprietary Global
  Water Intelligence DesalData, provided to the journalists who built the repo. Codex's
  "must not be treated as an open authoritative plant/outfall registry" line is correct,
  not overcautious — this is a genuinely good catch, not present in Claude's own
  second-pass draft.
- The `Effluent`/`EUTROPY` unverified-citation issue Claude flagged after the Gemini
  research pass **was caught and handled at least as well by Codex**: gated behind an
  explicit smoke test (licence, API, maintained status, salinity-brine applicability)
  before adoption, with a clean fallback ("initial dilution remains a cited parameter
  range" if it fails) — see §5.2 and §11. No pushback needed here; confirmed aligned.

**Where Codex's merge improved on Claude's own second-pass draft (adopted without
dispute):**
- **Strategy A (constant/status-quo) must be feasible, not just evaluated.** Claude's
  earlier draft treated an infeasible constant-production baseline as informative in
  its own right. Codex's correction is right: for the *main* comparison, an infeasible
  baseline confounds the result — a strategy that fails to meet demand trivially looks
  environmentally "better" by producing less water, which is the same curtailment-gaming
  failure mode already guarded against in the coordinated-vs-independent comparison
  (§6.4). Claude's original framing survives only as a labeled secondary stress test,
  not the headline benchmark.
- **The coordination-dominance test invariant needed its precondition stated.** Claude's
  earlier drafts asserted "coordinated should never do worse than independent" as a test
  to write. Codex correctly points out this only holds when the combined independent
  schedule is actually feasible *in the coordinated model* and re-evaluated under the
  same joint objective — not automatically, and not when quota/information constraints
  give the two strategies genuinely different feasible sets. Adopted as stated in §9.
- **"Coincidental dumping" framed as a hypothesis to test, not an asserted fact about
  the eventual corridor.** Sharper and more honest than Claude's phrasing.
- `docs/prior_art_adaptation.md`, `data/registry/`, and the two-tier "closed decisions
  vs. evidence-dependent gates" structure in §11 are all real improvements in
  reproducibility/honesty bookkeeping that Claude's draft didn't have.

**Where this cross-check pushed back / patched a gap (Claude's addition, not silently
dropped):**
1. **The corridor dispute was narrowed further than it should have been, without
   engaging the counter-consideration Claude had raised.** Codex's merge settles on
   Jubail/Ras Al-Khair (Gulf) as "the first candidate" / intended headline case — which
   happens to match Claude's own original lean, so this isn't a case of Codex
   overriding Claude's position. But Claude's *update after the Gemini research pass*
   had added a real, specific counter-consideration this final merge doesn't mention
   anywhere: the Red Sea has a purpose-built regional current model (SMORS, CMEMS-derived,
   eddy-resolving 1/24°) with no named Gulf equivalent — Gulf coverage falls back to the
   coarser global 1/12° CMEMS product. Codex's gating structure (conditional on
   resolution/provenance checks, hybrid-domain fallback if they fail) is sound
   engineering practice and is **kept as-is** — but the text is patched below (§4.2,
   §11) to state the SMORS trade-off explicitly as the reason Gulf was still chosen
   *despite* it (plant-documentation quality weighted more heavily than current-model
   resolution for a first candidate), rather than reading as if the Red Sea option was
   never considered. This is a real, remaining judgment call, not a closed question —
   see the honest-status verdict below.
2. **PHREEQC explicitly out of scope.** Both independent early drafts noted this;
   Codex's final merge dropped it from the non-goals list. Re-added to §2 — cheap, and
   avoids a specific, plausible scope-creep temptation (this candidate's brine
   chemistry only needs mass-balance arithmetic; full speciation belongs to the
   separate brine-mineral-TEA candidate in RESEARCH.md).
3. **A required-vs-stretch line inside the flexibility/scenario matrix.** Codex's
   benchmark design (§7) is thorough — 3 strategies × 5 flexibility scenarios × ~10
   scenario types — but doesn't state how much of that cross-product is actually
   required for the headline result within 5 weeks, versus pursued as time allows. Each
   individual solve is cheap; the surrounding engineering/write-up overhead per
   combination is not. Re-added as an explicit required-subset line in §7 and the
   Phase 3 gate in §10.

### Honest alignment verdict

**Aligned**, with one specific, named exception. Every substantive technical
disagreement from the two build-plan drafts (analytical-vs-numerical transport model,
benchmark mechanism, tools/-vs-package boundaries, Pyomo+HiGHS, the linear-kernel
invariant) converged to the same answer across both independent merges, and the newly
verified citations hold up. The one thing that is **not** actually resolved, and
shouldn't be reported as resolved, is the Gulf-vs-Red-Sea corridor choice: both agents
independently lean Gulf/Jubail, for a real and stated reason (public plant-capacity
documentation), but neither has weighed that against the Red Sea's better regional
current model in a way that constitutes an actual decision — it's a default, gated on
Phase 4 empirical checks, not a considered-and-closed choice. That's fine to proceed
with (the plan doesn't need it settled before Phase 0–3), but it should be named as
still open, not papered over as decided.

---

## 1. What the prototype must prove

> Under realistic limits on desalination-plant turndown, train cycling, potable-water
> storage and transmission, how much can coordinated multi-plant production dispatch
> reduce cumulative coastal salinity-exposure proxies relative to constant and
> plant-by-plant operation?

A successful prototype provides reproducible evidence for four linked claims:

1. Multiple outfalls can create time-dependent cumulative exposure that is missed when
   each plant is assessed only against its own plume.
2. Brine flow is an unavoidable consequence of water production and recovery;
   flexibility comes from production allocation and **product-water storage**, not
   assumed brine storage.
3. A fast, transparent transport-response model can place the cumulative constraint
   inside a rolling-horizon optimizer.
4. The value of coordination can be isolated quantitatively while holding demand,
   reserve, plant, and cost assumptions constant.

The prototype will **not** claim biological damage, regulatory compliance, real-site
accuracy, autonomous control, or a measured percentage improvement before the model is
actually run.

## 2. Deliverable boundary

**Minimum viable scientific deliverable:** a canonical 2D coastal corridor (three
plants, one or two product-water reservoirs, demand profile, bathymetry, spatially/
time-varying currents, background salinity, habitat/receptor polygons, configurable
outfall properties); a time-dependent far-field salinity-anomaly model with source
superposition, advection, anisotropic dispersion, boundary exchange, decay/flushing,
and a parameterized near-field initial-dilution factor; a precomputed source-to-receptor
kernel per forecast scenario; a rolling-horizon LP/MILP dispatch model evaluated over
the ensemble; three core benchmarks (constant, independent, coordinated); sensitivity
runs (flexibility, storage, forecast error, dispersion, threshold, penalty weight); and
standardized tables/plots/maps/manifests/report generated only from saved results.

### Explicit non-goals before September 30

Full Red Sea or Arabian Gulf simulation; a high-resolution 3D baroclinic hydrodynamic
model; resolving negatively buoyant near-field jets or diffuser geometry from first
principles; dedicated brine storage; site-specific coral/seagrass/benthic mortality
predictions; real SCADA integration or closed-loop control; a production SaaS platform;
claims about a particular Saudi plant without operator data and calibration.

**Also explicitly out of scope: a PHREEQC-style geochemical speciation model.**
$Q_{b,i}(t)$ and brine salinity only need standard SWRO mass-balance arithmetic (feed
salinity, recovery ratio) — full ion speciation belongs to the separate brine-mineral-
TEA candidate (RESEARCH.md's Z1/BrineTrain), not this one. A live plant-registry
scraper is similarly out of scope: the cluster's plant list is small and static enough
that manual, cited curation is the right level of effort.

## 3. Repository structure

```text
.
├── BUILD_PLAN.md
├── pyproject.toml
├── Makefile
├── docs/
│   └── prior_art_adaptation.md    # commit hashes, licences, adopted equations — see §6.6
├── configs/
│   ├── canonical_corridor.yaml
│   ├── benchmarks.yaml
│   └── schemas/
├── data/
│   ├── README.md
│   ├── raw/                 # cached immutable subsets; gitignored
│   ├── processed/           # normalized Zarr/NetCDF/Parquet; gitignored
│   ├── synthetic/            # small canonical domain — committed
│   ├── registry/              # cited plant assumptions and threshold ranges
│   └── manifests/               # URLs, queries, checksums, licences, timestamps
├── src/brineguard/
│   ├── config.py
│   ├── schemas.py
│   ├── domain.py
│   ├── data/
│   │   ├── bathymetry.py
│   │   ├── currents.py
│   │   └── normalize.py
│   ├── transport/
│   │   ├── grid.py
│   │   ├── solver.py        # numerical conservative solver — independent cross-check
│   │   ├── analytical.py    # closed-form source–receptor kernel — primary
│   │   ├── kernels.py       # kernel builder + content-addressed cache
│   │   └── validation.py
│   ├── dispatch/
│   │   ├── model.py
│   │   ├── baselines.py     # constant / independent / coordinated
│   │   ├── rolling.py
│   │   └── solution.py
│   ├── experiments/
│   │   ├── scenarios.py
│   │   ├── runner.py
│   │   └── metrics.py
│   ├── reporting/
│   │   ├── plots.py
│   │   ├── tables.py
│   │   └── report.py
│   └── cli.py
├── tests/
│   ├── fixtures/
│   ├── golden/
│   ├── test_transport.py
│   ├── test_kernel.py
│   ├── test_dispatch.py
│   └── test_benchmarks.py
├── runs/                    # immutable run directories; gitignored except examples
└── tools/
    ├── README.md
    ├── fetch_gebco.py
    ├── fetch_copernicus.py
    ├── fetch_hycom.py        # fallback, built only if needed
    ├── check_html_artifact.py
    ├── verify_environment.py
    ├── audit_provenance.py
    ├── package_evidence.py
    ├── gemini_deep_research.py   # already built
    └── gemini_flash.py           # already built
```

`notebooks/` (optional, exploratory only) may exist, but no result used in the
application may live solely in a notebook cell.

## 4. Data plan

### 4.1 Validation fixture first

The first end-to-end run must not depend on external credentials or uncertain Saudi
outfall data. `brineguard.domain` generates a deterministic canonical corridor from
YAML: rectangular/gently-curved coastline, open-ocean boundary, land mask, variable
depth; three outfalls with distinct locations, nominal production, recovery, brine
salinity, turndown, ramp, and train sizes; one shared or two interconnected
product-water reservoirs; hourly demand/tariff profiles; steady/tidal/reversing/
forecast-error current fields; synthetic habitat/receptor polygons at near/cross/
downstream locations. Every field carries units, CRS where relevant, seed, and
provenance. Committed to the repo so CI and reviewers can verify the algorithms without
downloading anything. **This is a validation fixture, not the intended headline Saudi
demonstration** — it exists to give the numerical solver a known answer to check
against, which reanalysis-driven data never provides.

### 4.2 Sourced representative corridor — intended headline case, still gated

After the synthetic pipeline passes, replace only the physical boundary fields — not
the architecture — with an openly sourced representative corridor. **The first
candidate is a bounded Jubail/Ras Al-Khair-area Gulf domain**, because several
desalination assets are publicly documented there — this matches both independent
drafts' original lean. **This choice is made despite, not because of, the ocean-current
data picture**: the Red Sea has a purpose-built regional downscaling (SMORS,
CMEMS-derived, eddy-resolving 1/24°) with no named Gulf equivalent, so Gulf coverage
falls back to the coarser global 1/12° CMEMS product (`GLOBAL_ANALYSIS_FORECAST_
PHY_001_024`). Plant-documentation quality was weighted more heavily than current-model
resolution for picking a *first* candidate — that is a judgment call, not a closed
technical question, and it should be named as such rather than presented as decided.
Selection is further conditional on demonstrating useful reanalysis resolution,
plausible plume interaction over the chosen domain, and a defensible water-network
coordination assumption (§11).

| Need | Preferred source | Fallback | Stored form | Caveat |
|---|---|---|---|---|
| Bathymetry | GEBCO 15-arc-second grid via OPeNDAP + `xarray` | synthetic bathymetry | normalized NetCDF/Zarr | No paywall/registration confirmed; slice the bounding box directly from the remote URL, never download the global grid. Resolution may still be too coarse near individual outfalls; no engineering-grade claim. |
| Currents/temp/salinity | Copernicus Marine (CMEMS) via the official `copernicusmarine` Python toolbox | HYCOM 1/12° OPeNDAP/NCSS (no registration) or synthetic ensemble | chunked Zarr, opened with `xarray`/`dask` | Confirmed free account, no volume/bandwidth quotas, native Zarr support. Global 1/12° product covers the Gulf; the Red Sea additionally has SMORS (1/24°) — see corridor note above. |
| Coastline/land mask | derived from bathymetry or Natural Earth | synthetic geometry | GeoJSON/NetCDF mask | No claim of precise shoreline/outfall geometry. |
| Outfalls & plant capacities | SWA/SWCC and project-owner documents first; curated industry/project sources second | explicitly synthetic plants | versioned CSV/GeoJSON | Public coordinates rarely establish exact diffuser position, flow, recovery, train count, or salinity. Never silently substitute plant centroids for outfalls. |
| Habitats/receptors | openly licensed habitat polygons if defensible | synthetic sensitivity zones | GeoJSON | Exposure receptors, not proof of ecological effect. |
| Thresholds | cited literature ranges, used in sensitivity analysis | generic excess-salinity thresholds | YAML with citations | Never present one universal absolute PSU limit — already the direction taken in `brineGuard-coast.html`'s fixes. |

`tools/fetch_gebco.py` creates a localized, checksummed subset without downloading the
global grid; `tools/fetch_copernicus.py` uses `copernicusmarine subset`/the Python API
and writes a chunked Zarr store, requesting only the bounding box, depth layer(s),
variables, and historical windows needed. `tools/fetch_hycom.py` is an adapter-
compatible fallback, built only if CMEMS access/coverage actually fails — and must not
silently mix HYCOM and CMEMS products within one experiment.

Authoritative references: [GEBCO](https://www.gebco.net/), [OPeNDAP](https://www.opendap.org/),
the official [Copernicus Marine Toolbox docs](https://toolbox-docs.marine.copernicus.eu/en/stable/).
Record the exact dataset IDs/versions selected by the fetch tools — provider names alone
are insufficient provenance.

Plant and threshold registries are manually curated, versioned, and source-cited in
`data/registry/`. Water-system interconnection, storage sharing, and dispatch authority
are separate facts from geographic proximity; where public evidence is absent, they are
explicit scenario assumptions, never asserted site facts.

### 4.3 Caching and provenance

Raw downloads are immutable. Every external subset gets a manifest: provider,
dataset/version, variable names, spatial/temporal query, retrieval time, licence URL,
request parameters, byte size, SHA-256 checksum. Processed data records the source
checksums and normalization code version. A run consumes a manifest ID, never an
unrecorded "latest" dataset — directly serving GPIW's Performance Measurability
criterion, not just engineering hygiene.

## 5. Marine transport model

### 5.1 Physical abstraction

Model the **far-field salinity anomaly** $c = S - S_0$ after a parameterized near-field
dilution factor, on a depth-averaged 2D grid:

```
∂(h c)/∂t + ∇·(h u c) = ∇·(h D ∇c) − λ h c + Σ_i m_i(t) δ(x − x_i)
```

where $h$ is depth, $u$ the forecast depth-averaged current, $D$ an effective
dispersion tensor, $λ$ unresolved flushing/decay, and $m_i$ the injected
salinity-anomaly load after near-field dilution:

```
Q_b,i(t) = P_i(t) (1 − R_i(t)) / R_i(t)
m_i(t)   = Q_b,i(t) [S_b,i(t) − S_0(x_i,t)]
```

A **screening model**. Dense gravity currents, bathymetric attachment, temperature,
chemicals, and diffuser jets are unresolved model discrepancy, named as such — not
silently absorbed.

### 5.2 Source–receptor kernel approach — resolved

The dispatch model uses a **precomputed linear source–receptor matrix** as its primary
marine representation: an analytical/semi-analytical depth-averaged advection-diffusion
response driven by piecewise forecast currents, built with `numpy`/`scipy`/`xarray` — no
heavy 3D solver as a runtime dependency. This resolves the earlier analytical-vs-
numerical disagreement between the two independent drafts in favor of the lighter
primary model, matching the Gemini research's source–receptor recommendation; the
tradeoff is explicit:

- the headline result is a regional **screening and coordination proof**, not a
  calibrated plume forecast;
- a small conservative numerical advection-diffusion solver remains an independent
  cross-check for mass balance, land/open boundaries, reversing currents, and selected
  schedules — this is where the analytical/numerical roles actually land, not a
  demotion of either;
- an open `Effluent`-style near-field model may be evaluated offline to estimate
  initial dilution, **but is not adopted until its API, licence, maintained status, and
  salinity-brine applicability pass a real smoke test** — confirmed as the right
  treatment of this unverified lead from the research pass, not taken on faith;
- EUTROPY/Delft3D/TELEMAC-class tools are reference or future validation paths, not
  dependencies for the September prototype.

CMEMS 3D currents convert to depth-averaged forcing via an explicit, thickness-weighted
rule over the locally represented water column, then interpolate to the screening grid.
Interpolation does not create near-shore information — report native product
resolution, temporal cadence, wet-cell distance from each assumed outfall, and any
extrapolation. Prefer the highest defensible hourly/three-hourly product; do not
manufacture tidal variability from a daily field.

State update for forecast scenario $\omega$:

```
c[t+1,ω] = A[t,ω] c[t,ω] + B[t,ω] m[t]
```

Precomputed impulse response from each outfall to each habitat/receptor and time:

```
c[x,t,ω] = c_bg[x,t,ω] + Σ_i Σ_{τ≤t} H[x,i,t,τ,ω] · m[i,τ]
```

$H$ is indexed by both release time $\tau$ and arrival time $t$ (not a stationary
$K(t-\tau)$) because forecast currents are nonstationary — matches the scenario-indexed
kernel already agreed in `brineGuard-coast.html`. Only receptor-level coefficients enter
the optimizer; full-grid fields are retained for maps and post-run verification.

**Linearity is an architectural invariant, not a preference.** For fixed scenario
forcing, recovery, background salinity, and transport parameters, source load is affine
in $P_i(t)$, and the precomputed convolution is linear in source load. The exposure
hinge is linearized with nonnegative auxiliary variables. No black-box simulator,
neural surrogate, concentration-dependent dispersion, or decision-dependent current
field may be inserted inside the optimizer if it breaks the LP/MILP structure —
nonlinear physics is offline-validation or ex-post evaluation only, unless separately
linearized and tested.

### 5.3 Transport validation gates

The solver/kernel cannot advance because plots look plausible. Required: zero source
produces zero anomaly; superposition and source scaling hold numerically; salt-anomaly
mass balance closes within a declared tolerance; the constant-current analytical case
agrees within tolerance; grid/timestep refinement changes receptor dose by less than a
declared percentage; direct solver and impulse-response reconstruction agree at all
benchmark receptors; open-boundary behavior and reversing currents don't create
negative salinity anomalies; held-out current scenarios are never used to tune
dispersion or thresholds. Report these validation errors alongside optimization
benefits — not separately, not omitted.

## 6. Dispatch optimizer

### 6.1 Library choice — locked

**Pyomo + HiGHS (`highspy`)**, independently recommended by the Gemini research pass
(converging with both drafts' original picks). `scipy.optimize.milp` is an emergency
fallback for a reduced LP/MILP only. **IPOPT is not part of the MVP** — it becomes
relevant only if a later pilot introduces continuous nonlinear hydraulic head-loss
equations, and adding it now would break the deliberately linear, auditable scope; it
remains a documented, not forgotten, escape hatch. OR-Tools/CBC/GLPK are not scheduled
for comparison unless HiGHS fails a recorded performance/capability gate on the actual
scenario size. Solver-specific code stays behind a small adapter so a later pilot can
swap solvers without touching domain logic.

### 6.2 Decision variables

$P[i,t]$ (potable-water production rate); $z[i,k,t]$ (train on/off status, train-
cycling scenario only); optional $\text{start}[i,k,t]$/$\text{stop}[i,k,t]$; $V[n,t]$
(product-water storage at reservoir $n$); $F[a,t]$ (transmission flow on arc $a$, if
more than one demand/storage node); $Q_b[i,t]$ and the salinity-anomaly load — **affine
expressions derived from $P$ and recovery, not freely schedulable variables**, the
load-bearing correction this whole candidate is built on; $e[r,t,\omega] \ge 0$
(exceedance proxy above receptor threshold); optional peak/CVaR auxiliaries once the
deterministic core works.

### 6.3 Constraints

Product-water mass balance with timestep/transmission losses; demand satisfaction and
minimum emergency reserve; reservoir capacity and terminal-storage condition
(preventing end-horizon depletion); plant/train min/max production; ramp, minimum
up/down time, starts, max cycling; recovery-dependent brine flow and salt-anomaly load;
outfall flow/dilution limits where modeled; water-purchase or daily production bands as
optional scenarios; one common near-term schedule across forecast scenarios, with
explicit non-anticipativity if recourse is added later.

### 6.4 Objective

```
min operating_cost
  + w_ramp · ramp/cycling_cost
  + w_exp · E_ω[ Σ_{r,t} area_r · Δt · max(0, S[r,t,ω] − threshold_r) ]
  + (optional) risk_weight · CVaR_α(total_exposure_ω)
```

**Do not hide the trade-off in a single chosen $w_{exp}$.** Produce a Pareto curve of
operating cost vs. exposure proxy. The headline comparison must either hold cost fixed
across strategies or report both cost and exposure — otherwise coordination could "win"
merely by curtailing water or spending without limit.

### 6.5 Rolling horizon

First solve a 48-hour perfect-forecast horizon. Then roll: optimize 48 hours, enact the
first 6, update state/storage/forecast, repeat. Forecast ensembles are the primary
uncertainty treatment; distributionally robust MPC and conformal prediction stay future
work.

### 6.6 Reference implementations and adjacent prior art

Inspect these before implementing plant scheduling — copy or vendor code only after
checking licence compatibility, tests, assumptions, and whether reuse is actually
faster than a small clean implementation:

- [`SanPen/DesalinationPlant`](https://github.com/SanPen/DesalinationPlant) — structural
  reference for desalination/microgrid scheduling and active-power constraints. No
  cumulative marine constraint; record exact files/ideas adapted in provenance.
- [`dw-data/desalination`](https://github.com/dw-data/desalination) — broad capacity/
  statistical priors for plausibility checks only. **Verified against its own README**:
  it's primarily FAO AQUASTAT country-level data; the plant-market capacity figures
  come from proprietary Global Water Intelligence DesalData, supplied to the DW
  journalists who built the repo. **Must not be treated as an open authoritative
  plant/outfall registry** — cite it for statistical plausibility ranges only, never
  for specific plant facts.
- Oikonomou & Parvania's FlexPWF framework — **verified**: *IEEE Trans. Smart Grid*
  11(6), pp. 4784–4794, 2020, DOI [`10.1109/TSG.2020.3000173`](https://doi.org/10.1109/TSG.2020.3000173).
  Co-optimizes flexible desalination/pump/storage assets with power and water
  distribution systems — the closest adjacent prior art for the coordinated-dispatch
  framing. Cite it and state the extension precisely: adding a multi-outfall
  source–receptor exposure constraint and testing environmental coordination, not
  claiming coordinated water production itself is new.

Create `docs/prior_art_adaptation.md` during implementation with repository commit
hashes, licences, inspected components, adopted equations, deviations, and citations —
prevents useful references from becoming unattributed or irreproducible borrowing.

## 7. Benchmark design: three strategies across flexibility scenarios

All strategies receive identical demand, initial storage, plant capacities, recovery,
ramp limits, current scenarios, thresholds, and cost data, evaluated ex post through
the same full transport solver.

**Strategy A — constant/uncoordinated operation.** Each plant holds its nominal
production share or invariant production profile; no marine forecast affects
production. **For the primary comparison, the fixed rate must be chosen so horizon
demand and terminal product storage are feasible** — an infeasible baseline would
confound the environmental comparison (a strategy that can't meet demand trivially
looks "better" by producing less, the same curtailment-gaming failure mode the
objective already guards against). An infeasible constant-production case is retained
only as a separate, clearly labeled stress test, not the headline benchmark.

**Strategy B — independently optimized plants, evaluated jointly.** Pre-allocate each
plant's production obligation and storage share. Each plant solves its own single-plant
model, optimizing energy and the exposure caused by its discharge alone at its
designated local receptors — it does not see other plants' contributions. Combine the
independently-chosen schedules and evaluate the **true joint exposure** with all
sources present, through the same direct transport/evaluation pipeline used everywhere
else. Because the allocation rule can bias this benchmark, **run at least two fair
allocation rules** (capacity-proportional and baseline-cost-minimizing) and disclose
both.

The expected gap has a precise mechanism, but isn't guaranteed to be large — the
exceedance function is non-separable across sources:

```
[a + b − threshold]₊  ≠  [a − threshold]₊ + [b − threshold]₊
```

Two individually acceptable contributions can jointly cross a threshold; Strategy B
cannot anticipate that interaction, Strategy C can. The experiment must *measure* the
gap and may legitimately find it small under some spacing/flushing/threshold/
flexibility conditions — this is a result to report either way, not an assumed win.

A named mechanism to test, from the Gemini research pass: **"coincidental dumping"** —
independently cost-optimized plants may ramp production at the same low-tariff hours to
refill product-water tanks, unintentionally synchronizing brine loads while currents
provide poor flushing. **Use this as a benchmark hypothesis to test, not an asserted
fact about whichever corridor ends up selected.** Report source-load synchronization,
overlap contribution, and whether coordination desynchronizes it.

**Strategy C — coordinated multi-plant dispatch.** Optimize all production, shared
storage/transmission, and cumulative receptor exposure jointly — aligned in spirit with
the FlexPWF framing (§6.6). The central comparison is **B vs. C under the same
flexibility scenario and operating-cost budget**:

```
coordination_benefit = (independent_exposure − coordinated_exposure) / independent_exposure
```

computed only at matched feasibility and cost.

### Operational-flexibility scenarios — not benchmark tiers

Run A–C where meaningful under: (1) no operational flexibility; (2) limited continuous
turndown (±5%, ±10%); (3) train-level cycling with start/minimum-run constraints;
(4) network flexibility across connected plants and storage; (5) optional dilution
allocation, kept clearly separate since it may need infrastructure or another water
stream. This resolves the current dashboard inconsistency: `brineGuard-coast.html`'s
four friendly "tiers" conflate operational flexibility with coordination strategy —
before real results are inserted, revise it to expose two controls, **strategy**
(constant/independent/coordinated) and **flexibility scenario** (none/turndown/train
cycling/network+storage), not one blended axis. The evidence table is always the
three-strategy ablation, stratified by flexibility scenario.

**Required for the headline result within the 5-week budget: scenarios {1, 2, 4} × all
three strategies × 2–3 scenario types from the matrix below.** Each individual LP/MILP
solve is cheap, but the surrounding engineering and write-up overhead per combination is
not — the remaining flexibility scenarios and scenario-matrix breadth are sensitivity
analysis pursued as time allows (Phase 4/5), not a Phase-3 gate requirement.

### Scenario matrix

For the sourced case, construct forecast scenarios from representative historical
reanalysis windows or a documented bootstrap of current-field errors, rather than
hand-inventing every ensemble member; synthetic scenarios remain necessary for
controlled mechanism tests. Steady alongshore current; tidal/reversing current;
low-flushing adverse period; forecast ensemble with direction/speed error; one plant
near a sensitive receptor; overlapping downstream plumes; low vs. high product-storage
availability; connected vs. constrained transmission; threshold and dispersion
uncertainty; optional plant-outage stress test.

### Primary metrics

Habitat/receptor area-hours above threshold; integrated excess-salinity exposure and
worst-scenario exposure; peak excess salinity and recovery time; water-demand deficit
and reserve violations (must be zero in feasible main cases); production energy/cost,
cycling, ramping, curtailment, dilution water; storage capacity and flexibility
required; the coordination-benefit ratio above; solver time, optimality gap, transport
reconstruction error, forecast generalization. All ecological outputs are called
**salinity-exposure proxies**, never a damage claim, unless a partner later supplies a
validated dose-response model.

## 8. Reusable infrastructure — build once, call repeatedly

### 8.1 `tools/` — operational/developer utilities, thin, call package functions

| Tool | Build when | Responsibility | Required behavior / done check |
|---|---|---|---|
| `fetch_gebco.py` | Before real-domain work | Slice GEBCO via OPeNDAP/xarray, hand a localized subset to the normalizer | No credential required; idempotent content cache; bbox CLI; checksum/licence/provenance manifest; `--offline`/`--force`; second identical call is a verified cache hit. |
| `fetch_copernicus.py` | Before real-domain work | `copernicusmarine` API/toolbox subset of currents/salinity/temperature into Zarr | Free-account credentials via documented env/config; bbox/depth/date/variable CLI; chunking; resume/retry; never logs credentials; manifest + cache; verified against a real subset. |
| `fetch_hycom.py` | Only if the CMEMS path fails | No-registration HYCOM fallback, same normalized-data contract | Never silently mixes HYCOM and CMEMS products in one experiment; records dataset/version and fallback reason; built on demand only. |
| `verify_environment.py` | First implementation day | Python version, solver availability, credentials, cache writability, library versions | Fast pass/fail; never prints secrets; `--json` option. |
| `check_html_artifact.py` | When HTML/report output is first connected | Generalized Playwright check replacing ad-hoc headless-Chrome commands | Local-file or URL mode; exercises configurable tabs/controls; captures console/page errors; screenshots to an explicit dir; asserts illustrative disclaimers are visible and no placeholder claims survive in final-result mode; demonstrably catches an injected test error. |
| `audit_provenance.py` | Before first evidence bundle | Every external dataset/result has a manifest, checksum, licence, config, code revision | Nonzero exit on missing lineage; compact audit report. |
| `package_evidence.py` | Final two weeks | Assemble configs/manifests/metrics/plots/report into a reproducible evidence bundle | Allowlisted inputs; refuses dirty/missing runs unless overridden; checksums; never includes raw credentials or oversized caches. |

The existing Gemini wrappers remain research tools and must not become runtime
dependencies of the scientific prototype.

### 8.2 `src/brineguard/` — domain behavior, importable, unit-tested

| Module/capability | Why reusable | Stable interface/output |
|---|---|---|
| Config loader + schema validator | Every run needs the same assumptions/unit checks | Validated typed config; resolved config saved with the run. |
| Synthetic-domain generator | Offline CI, ablations, demos, fair comparisons | Seeded `xarray.Dataset` + GeoJSON/CSV assets + manifest. |
| Provider adapters + normalizer | Separates external data formats from physics | Canonical variable names, coordinates, masks, units, calendars. |
| Conservative transport solver | Kernel creation, direct verification, maps, ex-post evaluation | `simulate(domain, sources, forcing) -> xarray.Dataset`. |
| Impulse-response/kernel builder | Avoids recomputing expensive source-response matrices per run | Content-addressed kernel store keyed by domain, forcing, params, receptors, timestep. |
| **Single parametrized** dispatch model builder | Prevents three strategy scripts from drifting apart while retaining different information sets/objectives | `build_dispatch(config, kernel, strategy={constant,independent,coordinated}) -> model`; structured solution object. |
| Rolling-horizon coordinator | Reuses dispatch/state-update consistently | Schedule, realized state trajectory, forecast metadata, solver diagnostics. |
| Baseline strategy library | Prevents benchmark definitions drifting between sessions | Named `constant`/`independent`/`coordinated` strategies, versioned. |
| Scenario generator | Makes uncertainty/sensitivity runs declarative | Seeded ensemble with weights + perturbation metadata. |
| Benchmark runner harness | Every method emits comparable artifacts | One run directory per experiment, fixed schema (§8.3). |
| Metrics library | Prevents percentages being recomputed differently in charts vs. prose | Tidy Parquet/CSV metrics + JSON summary; units/denominators explicit. |
| Plot/report generator | One source of truth for deck figures, dashboard data, technical appendix | Deterministic PNG/SVG/HTML/table artifacts, generated only from saved result files. |
| Run/provenance manager | Reproducible, cacheable results | Immutable run ID, resolved config, seed, git revision, environment, input hashes, timings. |

### 8.3 Standard run-output contract

```text
runs/<run_id>/
├── manifest.json
├── config.resolved.yaml
├── environment.json
├── inputs.json
├── schedule.parquet
├── storage.parquet
├── receptor_salinity.zarr
├── spatial_summary.nc
├── metrics.csv
├── metrics.json
├── solver.json
├── validation.json
├── figures/
└── report.html
```

**The dashboard must read `metrics.json` (or a generated JS data artifact) — it must
never contain manually typed prototype percentages.** This is the actual pipeline fix
for the exact problem patched cosmetically (via disclaimers) in `brineGuard-coast.html`
last session. A separate explicit `demo_mode: true` may generate illustrative values,
always watermarked as such.

### 8.4 Commands worth stabilizing early

```bash
python -m brineguard domain generate -c configs/canonical_corridor.yaml
python tools/fetch_gebco.py --config configs/open_corridor.yaml
python tools/fetch_copernicus.py --config configs/open_corridor.yaml
python -m brineguard transport validate -c configs/canonical_corridor.yaml
python -m brineguard kernels build -c configs/canonical_corridor.yaml
python -m brineguard benchmark run -c configs/benchmarks.yaml
python -m brineguard report build --run runs/<run_id>
python tools/check_html_artifact.py brineGuard-coast.html --out artifacts/browser
python tools/audit_provenance.py runs/<run_id>
```

CLI names can change once, before implementation; the separation of concerns should
not. Add a root `Makefile` as a discoverability layer — not a second implementation
layer — with targets like `make verify`, `make fetch-data`, `make smoke`, `make
benchmark`, `make report`, `make check-html`, `make test`, all calling the stable CLIs
above.

## 9. Testing and reproducibility policy

Fixed seeds for synthetic scenarios, all seeds recorded. Unit-test dimensional
conversions and the brine-production equation. Property-test nonnegative states,
superposition, monotonic source scaling, storage balance, demand conservation.

**Test the coordination-dominance property only under its actual mathematical
precondition**: first verify the combined independent schedule is feasible in the
coordinated model, evaluate it with the same joint objective, *then* assert the
coordinated optimum is no worse within solver tolerance. Do not apply this assertion
when quota or information constraints give the strategies genuinely different feasible
sets — this is not automatic, and asserting it blindly would be a bug, not a check.

**Test solve-independently/evaluate-jointly explicitly**: the reported independent
exposure must be recomputed from the combined schedules, never summed from plant-local
objective values — an easy, silent implementation bug that would defeat the entire
point of the benchmark.

One tiny "smoke" case that runs in seconds; one canonical golden benchmark that runs
locally in minutes. Golden tests check schemas, feasibility, and mass balance with
broad numerical tolerances — **not** an overfitted exact objective value. CI stays
offline; network-dependent data tests use cached fixtures, separately marked. Pin
direct dependencies; record the complete environment in every evidence run. No chart or
written claim may be generated from an in-memory result that wasn't saved with its run
manifest. **A benchmark failure or infeasible strategy is a result to explain, not
something to suppress.**

These invariants live in `tests/` and run on every results-affecting change.
`tools/audit_provenance.py` and `tools/check_html_artifact.py` stay workflow checks
because they inspect external artifacts and full run bundles, not unit-level scientific
behavior.

## 10. Five-week implementation sequence and gates

**Phase 0 — architecture lock and environment (1–2 days).** Lock the reconciled stack,
pin dependency versions. Create package skeleton, schemas, canonical config,
environment verifier, tests, run-output contract. Build/verify the GEBCO/Copernicus
fetchers; start caching candidate real-domain subsets in parallel so data access
doesn't become a late blocker.
*Gate: clean install, offline smoke test, HiGHS solver check, deterministic
synthetic-domain generation.*

**Phase 1 — linear kernel and transport validation (5–6 days).** Implement the
analytical/semi-analytical source–receptor kernel on the synthetic domain; implement
the small conservative cross-check solver; add superposition, analytical, mass-balance,
convergence, boundary tests; generate direct multi-source plume-overlap cases and
verify cached-kernel reconstruction.
*Gate: validation report passes declared tolerances; no optimization yet.*

**Phase 2 — deterministic dispatch (5–6 days).** Finalize content-addressed kernel
caching; implement storage, demand, production, recovery/brine, ramp, terminal
constraints; solve constant and coordinated perfect-forecast cases.
*Gate: zero water-balance violations, kernel error reported, schedules re-simulated
through the direct transport model.*

**Phase 3 — independent benchmark and rolling horizon (4–5 days).** Formalize
independent quotas and local receptor objectives; add both allocation-rule variants;
implement rolling horizon and the three-strategy harness.
*Gate: all methods use identical inputs and produce the standard output contract;
coordination benefit computed only at matched feasibility/cost; **headline result
covers flexibility scenarios {1,2,4} × 2–3 scenario types (§7) — the full matrix is
Phase 4+ stretch, not required here.***

**Phase 4 — uncertainty and sourced-domain demonstration (4–5 days).** Add
current/dispersion forecast ensembles and common-schedule evaluation; run
flexibility/storage sensitivity; run the sourced representative-corridor demonstration
if resolution, provenance, and geometry checks pass — **if they fail, report why and
use an explicitly hybrid domain (real bathymetry/currents with assumed plants) rather
than implying site accuracy.**
*Gate: held-out ensemble results, uncertainty intervals, sensitivity plots exist; no
site-specific claim without adequate data.*

**Phase 5 — evidence package and application (5–6 days).** Freeze one benchmark
configuration before inspecting final headline results. Generate figures/tables/report
solely through reporting modules. Run provenance, browser, and reproducibility checks.
Update the strategy dashboard to consume real `metrics.json`; keep a visible demo
watermark on any panel that remains illustrative. Prepare technical appendix, pitch
deck, video, limitations, and Saudi shadow-pilot plan.
*Gate: a fresh environment reproduces the selected evidence bundle from committed
config and cached/committed inputs.*

Remaining days are contingency for numerical instability, infeasible dispatch
assumptions, data-access failure, or model simplification.

## 11. Closed decisions and remaining empirical gates

**Closed by the Gemini research pass (architectural, not evidence-dependent):**

1. Marine ROM: analytical/semi-analytical linear source–receptor kernel
   (`numpy`/`scipy`/`xarray`); small conservative Eulerian solver for independent
   checks — not a particle model or full coastal CFD stack.
2. Bathymetry: GEBCO subset via OPeNDAP + xarray.
3. Ocean forcing: CMEMS primary via the official `copernicusmarine` toolbox into
   chunked Zarr; HYCOM OPeNDAP fallback only.
4. Optimization: Pyomo + HiGHS; no IPOPT unless later nonlinear hydraulics are
   explicitly authorized and justified.
5. Uncertainty: representative historical CMEMS windows and documented
   perturbation/bootstrap ensembles; no conformal/distributionally-robust extension in
   the MVP.
6. Runtime coupling: optimizer consumes a cached linear kernel; it never calls a
   nonlinear plume model inside the solve.

**Still open — evidence-dependent, not decidable from research alone:**

- Does CMEMS resolve the selected near-shore corridor well enough to justify a
  real-domain demonstration, or must it be labeled a regional forcing field over
  assumed local mixing?
- Are sourced plant locations exact outfalls, approximate plant sites, or unusable? The
  registry must encode location type and uncertainty.
- Is there evidence of shared product-water storage/transmission and dispatch
  authority? If not, connectivity remains a scenario assumption.
- Which threshold ranges have defensible primary-source support? The headline metric
  defaults to **excess salinity above local background**, swept over a cited range,
  never one absolute PSU cap.
- Does an `Effluent`-style library pass the licence/API/applicability smoke test, or
  should initial dilution stay a cited parameter range?
- Does the independent strategy actually exhibit coincidental dumping, and under which
  tariffs, currents, storage levels, and plant spacing? A result, not an assumption.
- **Genuinely unresolved judgment call, named explicitly (§0):** Gulf/Jubail vs. Red
  Sea as the sourced corridor — Gulf leads on public plant documentation, Red Sea leads
  on regional current-model resolution (SMORS). Both drafts default to Gulf without
  fully weighing this trade-off; it should be revisited once the Phase 4 resolution
  checks actually run against both, not left as an unexamined default if time allows a
  real comparison.

Any evidence-driven change must preserve the canonical data schema, linear-kernel
interface, three-strategy benchmark, and run-output contract.

## 12. Recommended first implementation slice

While the GEBCO/CMEMS fetchers cache sourced inputs in parallel, implement one offline
vertical slice before dashboard integration:

1. Generate a 40×60 synthetic coastal grid with three outfalls and four receptors.
2. Simulate one conservative tracer pulse; validate mass balance against the analytical
   case.
3. Build the source-to-receptor impulse-response matrix.
4. Solve a 24-hour continuous-production LP with one product-water tank.
5. Re-simulate the optimized schedule through the direct transport solver.
6. Emit the complete standard run directory (§8.3) and one comparison figure.
7. Rerun it from a clean command using only the saved config.

This tests every architectural boundary cheaply — domain generation, transport
correctness, kernel reconstruction, dispatch, the run-output contract, and
reproducibility — before adding train binaries, rolling horizons, forecast ensembles,
open ocean data, maps, or the HTML dashboard.
