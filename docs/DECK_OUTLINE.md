# GPIW deck skeleton (≤20 slides, maps all 8 equally-weighted criteria)

Rule: every number traces to docs/CLAIMS.md; nothing exceeds it. Criteria
coverage tags in [brackets] — all eight must appear, they carry 12.5% each.
Build target: PDF ≤20 MB. Draft in this file, design pass later.

1. **Title** — BrineGuard Coast: coordinated desalination dispatch for coastal
   protection. Track A (TRL 1–3), Individual innovator. One-line thesis:
   *same water, same energy spend, ~one-fifth less salinity stress — by
   coordinating when and where plants produce.*
2. **The problem** [Clear Market Need] — desal-heavy coasts; brine locked to
   production; multiple outfalls, shared receptors; today nobody schedules
   for the sea. (Coast schematic.)
3. **The insight** [Audacious Vision] — brine can't be stored, but production
   can be *moved* — in time (storage, tariffs) and space (between plants).
   The sea's response is linear → the whole problem becomes auditable
   optimization.
4. **How it works** [Technical Excellence] — kernel-as-transfer-function
   diagram: analytic Gaussian-puff kernel (tidal currents, exact integral) →
   LP dispatch → re-simulated through an independent FD solver → audited.
5. **Validation discipline** [Technical Excellence, Performance Measurability]
   — two independent methods must agree; mass balance closes 1e-6; optimizer
   never grades itself; 82 automated tests incl. tests of the auditors;
   adversarial audit by an independent frontier model, findings fixed.
6. **Headline result** [Performance Measurability] — C1: 18.6–20.9% exposure
   reduction at no greater energy cost; benefit chart; flex1=0 fairness proof.
7. **Robustness** — C3: positive on all 20 forecast members (min 14.5%),
   cost cap binding; uncertainty-interval figure.
8. **The trade-off, published** — C4 Pareto frontier figure: +10.7% budget →
   −27% exposure; decision stays with managers.
9. **When it does NOT help — and knowing in advance** [Technical Excellence,
   honesty] — C5: real Red Sea bathymetry null result + the screening bound
   (dose-asymmetry × flexibility) that predicted both outcomes ex ante. The
   tool tells you where coordination pays *before* you deploy it.
10. **Real-world grounding** [Scalability & Feasibility] — GEBCO bathymetry
    with cryptographic provenance; CMEMS current pipeline ready; hybrid
    labeling discipline (assumed plants/currents stated on every artifact).
11. **Deployment model** [Scalability & Feasibility, Durability & Safety] —
    shadow/advisory mode only; rolling 48h horizon (implemented, 96h tested);
    operator-in-the-loop; never controls plants directly. Fallback topology:
    single-owner IWPP fleet (no inter-utility governance needed).
12. **Lifecycle & environment** [Life-Cycle Impact] — {PENDING: screening LCA
    — energy-neutral by construction (cost-capped), compute footprint,
    avoided monitoring/mitigation burdens; societal framing}.
13. **Safety & failure modes** [Durability & Safety] — {PENDING: FMEA table —
    bad forecast → ensemble guard; solver failure → constant-schedule
    fallback; data loss → shadow mode is advisory; cyber boundary}.
14. **Market & who buys** [Clear Market Need, Long-Term Viability] —
    {PENDING: buyer hypothesis (regulator-driven IWPP compliance vs utility
    fleet operator), avoided-cost logic, incumbent-workflow findings from
    interviews}.
15. **Stakeholder validation** [Clear Market Need] — {PENDING: interview
    findings + letter(s) — docs/OUTREACH.md log}.
16. **Novelty & prior art** [Technical Excellence, Audacious Vision] —
    {PENDING: landscape table from adw_data/prior_art_research.md; the
    narrow claim: multi-plant hourly reallocation against shared cumulative
    receptor exposure at matched cost}.
17. **Roadmap to pilot** [Audacious Vision, Scalability] — calibrate with
    CMEMS/operator data → Saudi shadow pilot (≤$250k support scope) →
    per-corridor screening service. Milestones with dates.
18. **Team & execution** [Long-Term Viability & Execution] — solo ChemE +
    the agent-factory build system (this prototype: ~6 phases, 82 tests,
    frozen evidence, in weeks); advisory circle {PENDING: names}.
19. **Business & IP** [Long-Term Viability] — {PENDING: licensing model,
    open-core vs proprietary decision after prior-art search, use-of-funds}.
20. **The ask / close** — what winning funds: calibration, pilot host,
    validation. Reproduce-everything footer: `make verify-evidence`.

## Slide budget check: 20/20. PENDING slides blocked on: LCA draft (gap 12),
## FMEA (gap 20), market notes (gap 9), interviews (gap 8 — user), prior-art
## research (running), business/IP (gap 15/16).
