# GPIW 2026 Track A — Deep Research Report

Research deliverable only. No prototype build has started. Compiled 2026-08-25.

## 0. Methodology

Research was run as three parallel deep-dive passes (WebSearch/WebFetch), each covering two of
GPIW's six thematic categories, surveying commercial/startup landscape, patents, and 2020–2026
academic literature, with an explicit mandate to reject generic "apply ML to X" framings already
commercialized and instead find structurally unsolved gaps. Each pass proposed ~5 candidate Track A
ideas per category (~30 total), scoped to what a solo person + AI tools can validate as a pure
computational/simulation prototype — no physical lab, no proprietary hardware, no field access.
That pool was narrowed to 15 for this report, then ranked and shortlisted to 5. Full raw research
notes (search logs, extended citations) are preserved in the scratchpad for reference; this
document is the synthesized deliverable.

---

## 1. Competitive Landscape by Category

### 1.1 Advanced Water Production & Desalination Technologies

ML-for-membrane-fouling-prediction and ML-for-membrane-material-discovery are **saturated** —
multiple 2024–2025 reviews already cover this exhaustively (explainable-AI ion-transport studies;
[Materials 2025](https://doi.org/10.3390/ma18040840); [PMC11755723](https://pmc.ncbi.nlm.nih.gov/articles/PMC11755723/)).
Capacitive deionization and forward-osmosis draw-solute research are active fields but centered on
materials synthesis (needs a physical lab) or already ML-augmented
([CDI review](https://www.tandfonline.com/doi/full/10.1080/14686996.2025.2546286);
[FO magnetic draw solute](https://www.sciencedirect.com/science/article/abs/pii/S0011916425006460)).
**[WaterTAP](https://watertap.readthedocs.io/en/stable/background/what_is_watertap.html)**
(NREL/NAWI, free, open-source Python/Pyomo) is a maintained process-simulation + techno-economic
platform for desal trains — a legitimate computational-only prototyping base for this category.

Saudi-relevant landscape event: **NEOM's Oxagon brine-mining complex** (Enowa/Itochu/Veolia JV,
~$1.5–2B, signed Dec 2022) was **discontinued in May 2024**, replaced by an RFP for conventional
SWRO with no brine mining
([Utilities Middle East](https://www.utilities-me.com/utilities/neoms-1-5-billion-state-of-the-art-desalination-project-cancelled)).
No public source explains why — a genuine open question with a concrete, computable answer.

### 1.2 Water Reclamation, Circular Economy & Zero Liquid Discharge (ZLD)

This is the hottest 2025–2026 subfield
([ecomena.org](https://www.ecomena.org/zero-liquid-discharge-and-brine-valorization-in-seawater-desalination/);
[Wiley 2026 review](https://onlinelibrary.wiley.com/doi/10.1002/wer.70342);
[Water 2025 cost-benefit study](https://doi.org/10.3390/w17192855)). Existing multi-crystallization
techno-economic-analysis (TEA) studies
([Separations 2022](https://doi.org/10.3390/separations9100295);
[Separations 2025](https://doi.org/10.3390/separations12100266)) all use **generic seawater
composition**, not actual Red Sea/Arabian Gulf brine chemistry (salinity ~41–42 ppt vs. global
~35 ppt, different ion ratios). **PHREEQC** (USGS, free, with a Pitzer database for high-ionic-strength
brines) is the open-source equivalent of commercial OLI Systems software and is usable by a solo
researcher. [Nature Water 2024](https://www.nature.com/articles/s44221-024-00327-1) provides a
strong energy/cost/land benchmark dataset for ZLD/MLD trains to compare against. Gulf desal already
discharges ~115 Mm³/day of brine, causing basin-scale salinity buildup
([Nature Sci Reports 2022](https://www.nature.com/articles/s41598-022-25167-5);
[Frontiers Marine Sci 2022](https://www.frontiersin.org/journals/marine-science/articles/10.3389/fmars.2022.845113/full)).

### 1.3 Water Efficiency, Conservation & Consumption Management

Moderately crowded around demand forecasting and behavioral analytics, but most models are
trained/validated on temperate-climate data. Intermittent water supply (IWS, affecting ~1.3B people
globally) has an active optimization literature (NSGA-II valve placement, PSO+pressure-driven equity
optimization) but treats equity/scheduling as separate from leak detection. A Nature Scientific
Reports paper quantifies real energy/carbon costs of intermittent supply in arid regions, confirming
it's a live, underexplored cost. Non-revenue water (NRW) benchmarking against billing-only data
(no sensors) is comparatively unexplored despite public utility datasets (e.g. IBNET) existing.

### 1.4 Digitalisation, Automation & Smart Water Management

The most commercially **saturated** category. Leak detection: ASTERRA (satellite SAR), WINT (AI
anomaly + auto-shutoff), TaKaDu (acquired by Suez), Fido Tech/Aquarius Spectrum (acoustic). Sparse-
sensor leak localization is now an active *academic* niche too — AquaSentinel (arXiv 2511.15870,
Nov 2025) and "Just One More Sensor Is Enough" (arXiv 2406.19900) both solve sparse-sensor
localization, but **both assume continuous/steady-state hydraulics**, not intermittent-supply
transients. Digital twins are dominated by incumbents (Schneider Electric+Air Selangor, ABB,
Innovyze/AWS) — all require a pre-existing **calibrated hydraulic model + GIS**, which many smaller
utilities lack; calibration-from-minimal-data is explicitly called "extremely complex, costly" in
the literature. An MDPI systematic review explicitly flags the absence of "end-to-end detection
models integrated with simulations or digital twins that capture [cyberattack] dynamics, quantify
impacts... and assess contributions to overall system resilience" — current cyber-resilience work is
siloed into IT-intrusion, hydraulic-anomaly, and mitigation research streams that don't talk to each
other. Saudi NWC/SWA strategic documents name SCADA, AI leak detection, and digital twins as active
priorities, and NWC has historically reported NRW >25–30% in parts of the network.

### 1.5 Environmental Sustainability & Water Resource Conservation

AI-based groundwater level/quality forecasting (LSTM, GNN, LightGBM) is **saturated**, with pilots
already run with national water agencies in Morocco/Tunisia claiming 85–92% forecast accuracy 18
months out
([MDPI Water](https://doi.org/10.3390/w18080937); [Springer](https://link.springer.com/article/10.1007/s12145-024-01533-x);
[ACS ES&T](https://pubs.acs.org/doi/10.1021/acs.est.5c09120)). Managed aquifer recharge (MAR) site
suitability via GIS + Multi-Criteria Decision Analysis is likewise mature, with Saudi-specific
applications already published
([Springer NW-KSA MAR](https://link.springer.com/article/10.1007/s11269-025-04131-8);
[Yalamlam watershed](https://link.springer.com/chapter/10.1007/978-3-031-80520-2_17)).

The real, literature-confirmed gap: **CORMIX and Visual Plumes**, the dominant commercial
brine-dispersion tools (including a documented Red Sea case at Yanbu), are explicitly
**steady-state and near-field-only** — structurally unable to model cumulative effects across
multiple outfalls
([ResearchGate](https://www.researchgate.net/publication/256692825);
[Academia.edu](https://www.academia.edu/89257340)). The literature specifically flags semi-enclosed,
low-flushing seas — **the Red Sea and Arabian Gulf by name** — as most vulnerable to salinity
buildup around outfalls
([ScienceDirect review](https://www.sciencedirect.com/science/article/pii/S2468584425001023);
[Springer](https://link.springer.com/article/10.1007/s13762-024-06263-7)). No public tool models
**cumulative, far-field, multi-outfall** salinity/ecological risk across a whole coastline of
desalination plants — exactly Saudi Arabia's real situation on both coasts.

### 1.6 Accessible & Cost-Effective Wastewater Solutions

Decentralized wastewater treatment is a booming *hardware* market ($24.6B→$75.7B by 2034), dominated
by vendors like Fluence (EcoBox) and 374Water
([market report](https://www.usdanalytics.com/industry-reports/decentralized-wastewater-treatment-systems-market);
[Fluence](https://www.fluencecorp.com/decentralized-plants-are-transforming-small-communities/)).
The Gates Foundation's Reinvent the Toilet Challenge (>$200M invested since 2011) produced
omniprocessor/pyrolysis/electrochemical toilets calibrated for African/South Asian informal-settlement
demographics and waste composition, **not** Gulf/arid contexts
([Gates Foundation](https://docs.gatesfoundation.org/documents/fact_sheet_reinvent_the_toilet_challenge.pdf)).

Real gaps: constructed-wetland design for hot/arid climates is an explicit literature gap —
"evidence remains fragmented... limits comparability and weakens direct translation to design
guidance," with evapotranspiration-driven salt concentration and clogging named as under-addressed
([ResearchGate](https://www.researchgate.net/publication/387626342);
[ScienceDirect](https://www.sciencedirect.com/science/article/pii/S2949823626001030)); HYDRUS-based
modeling exists in individual papers but isn't packaged as a reusable design/optimization tool.
Low-cost pathogen sensors and QMRA (quantitative microbial risk assessment) frameworks are each
separately mature, but nobody has combined them into a sensor-*placement* optimization problem for
decentralized reuse networks.

---

## 2. Candidate Ideas (15)

| # | Idea | Category |
|---|------|----------|
| D1 | Gulf-brine-calibrated redesign of NEOM's cancelled brine-mining economics (PHREEQC TEA using real Red Sea/Gulf brine assay data vs. NEOM's actual cost/energy inputs) | Desalination |
| D2 | Gulf-specific exergy/second-law thermodynamic-limit benchmark for hybrid thermal-membrane desal trains (WaterTAP) | Desalination |
| D3 | SWRO pretreatment design Pareto optimizer (capital vs. energy frontier, differentiated from saturated fouling-prediction ML literature) | Desalination |
| Z1 | KSA/Gulf-brine-calibrated multi-mineral value-stacking TEA — joint water-recovery + mineral-revenue + carbon-cost optimizer across a ZLD train (PHREEQC + Pitzer) | ZLD |
| Z2 | Renewable-coupled ZLD train configuration optimizer (PV/CSP hybrid sized to KSA solar resource, benchmarked vs. Nature Water 2024 dataset) | ZLD |
| E1 | Heatwave-aware nonstationary demand forecasting for desert cities (vs. temperate-trained baselines) | Water Efficiency |
| E2 | Sensor-free NRW estimation via cross-utility ML benchmarking (billing/production data only, no field sensors) | Water Efficiency |
| G1 | Cyber-physical (SCADA + hydraulic) resilience co-simulation benchmark — literature-confirmed gap | Digitalisation |
| G2 | Model-free self-calibrating digital twin construction for GIS-less/uncalibrated utilities | Digitalisation |
| G3 | Zero-break-history pipe-failure transfer-learning meta-model for cold-start utilities | Digitalisation |
| S1 | Cumulative multi-outfall brine plume & ecological-risk model for the Red Sea/Gulf coastline | Environmental Sustainability |
| S2 | Dynamic MAR site + recharge-schedule optimizer (vs. static suitability-map baseline) | Environmental Sustainability |
| S3 | Agent-based groundwater-extraction policy stress-test (metering/pricing/quota scenarios) | Environmental Sustainability |
| W1 | Climate-adapted constructed-wetland design optimizer for arid/hot climates (Richards-equation/HYDRUS-style, vs. temperate EPA guidance) | Wastewater |
| W2 | Fecal-sludge/omniprocessor economics simulator calibrated to Gulf demographics (vs. Africa/South-Asia-calibrated tech) | Wastewater |

---

## 3. Scoring

Scored 1–5 on: **Novelty** (vs. state of the art), **Impact** (magnitude/measurability of the
benchmark result), **Feasibility** (buildable solo + AI, purely computational, open data),
**Saudi Relevance**, and **8-Criteria Fit** (holistic estimate against GPIW's assessment rubric).

| # | Novelty | Impact | Feasibility | Saudi Rel. | 8-Crit Fit | Avg |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| **S1** | 5 | 5 | 4 | 5 | 5 | **4.8** |
| **D1** | 4 | 4 | 5 | 5 | 4 | **4.4** |
| **Z1** | 5 | 4 | 4 | 5 | 4 | **4.4** |
| **E2** | 3 | 4 | 5 | 5 | 4 | **4.2** |
| **G1** | 5 | 4 | 4 | 4 | 4 | **4.2** |
| W1 | 4 | 4 | 4 | 4 | 4 | 4.0 |
| D2 | 3 | 3 | 5 | 4 | 3 | 3.6 |
| G2 | 4 | 4 | 3 | 4 | 3 | 3.6 |
| E1 | 3 | 3 | 4 | 4 | 3 | 3.4 |
| Z2 | 3 | 3 | 4 | 4 | 3 | 3.4 |
| G3 | 4 | 3 | 4 | 3 | 3 | 3.4 |
| S2 | 3 | 3 | 4 | 4 | 3 | 3.4 |
| D3 | 2 | 3 | 5 | 3 | 3 | 3.2 |
| S3 | 3 | 3 | 4 | 3 | 3 | 3.2 |
| W2 | 3 | 3 | 4 | 3 | 3 | 3.2 |

D1 and Z1 both hinge on the same underlying finding (no published TEA uses real Gulf/Red Sea brine
chemistry) — they're framed under different categories (Desalination vs. ZLD) but are effectively
one idea with two possible category submissions. They are merged into a single shortlist entry
below, freeing a slot for category diversity.

---

## 4. Top 5 Shortlist

**1. Coordinated Multi-Plant Desalination Production & Environmental Dispatch — Environmental
Sustainability & Water Resource Conservation.** *(Revised after cross-validation with an
independently-run parallel research effort — see §5.1 for provenance.)* CORMIX, Visual Plumes,
PLUMES2.0 and BrIHne, the standard brine-dispersion tools (including a documented Yanbu Red Sea
case), are structurally steady-state and near-field-only; no public tool aggregates cumulative,
time-resolved salinity buildup across a whole coastline of desalination outfalls, even though the
literature explicitly names the Red Sea and Arabian Gulf as the semi-enclosed seas most vulnerable to
this. That basin-scale gap is real and independently confirmed, but the first-draft framing of
"schedule brine discharge" turned out not to be physically credible: meaningfully shifting brine
release timing would require dedicated corrosive-brine storage on the order of 10⁵–10⁶ m³ for a
mid-size plant — reservoir-scale infrastructure, not a software-overlay assumption (brine storage at
that scale is corrosion-limited and capex-heavy; evaporator/crystallizer-class infrastructure alone
can run 60–70% of total ZLD process cost). Brine discharge rate is a *byproduct* of production, not
an independently controllable variable.

The corrected mechanism uses flexibility that genuinely exists in SWRO operation, confirmed via
established literature: time-varying production with product water (not brine) as the storage medium
under a MINLP formulation ([Ghobeity & Mitsos 2010, *Desalination*](https://www.avt.rwth-aachen.de/cms/avt/forschung/sonstiges/publikationen/~iavo/details/?file=571016&lidx=1)),
and variable-feed-pressure operation that keeps all RO trains online while varying recovery/production
without accumulating brine, as implemented at Sorek's "pressure center" design
([IDE Technologies](https://ide-tech.com/en/ide-water-technologies-pioneers-sustainable-desalination-with-sorek-2-beer-miriam/)).
The prototype: decision variables become each plant's production level / active-train count (which
determines its brine-discharge rate as a downstream consequence), draw/replenishment of *existing*
potable-water storage, and production allocation across a hydraulically interconnected multi-plant
coastal cluster — constrained by hourly/daily demand, storage capacity and minimum reserve,
transmission/interconnection limits, plant min/max load and ramping limits, and water-quality/blending
requirements. This is coupled to the same basin-scale cumulative-dose transport layer as the original
concept — a simplified box/advection-diffusion model driven by open GEBCO bathymetry and Copernicus
Marine/HYCOM current reanalysis, benchmarked against published coral/seagrass salinity-tolerance
thresholds. The prototype explicitly scopes itself to a synthetic interconnected coastal cluster
(representative of conditions where Saudi plants share transmission/coordinating authority), stated
as an assumption rather than claimed to hold for every Saudi plant.

Quantitative benchmark: three-way comparison of (a) status-quo independent constant/nominal
production per plant, (b) each plant optimizing its own production/storage independently (isolates
the value of temporal flexibility alone), and (c) coordinated multi-plant dispatch (isolates the
additional value of coordination) — reported as reduction in cumulative habitat-area-hours above
salinity threshold and worst-case near-outfall dose, versus energy cost and storage/demand-service
constraints satisfied. Differentiator: it's the only framing in the landscape that treats desalination
dispatch as a basin-scale coordination problem using flexibility levers that actually exist in SWRO
operation, rather than either a passive per-plant compliance map or an assumption of brine
inventory that isn't physically buildable.

**2. Gulf-Brine-Calibrated Mineral Valorization & Mining-Economics TEA (Z1/D1) — Water Reclamation,
Circular Economy & ZLD.** Every published ZLD/brine-mining techno-economic study found uses generic
seawater composition (~35 ppt, global average ion ratios), not actual Red Sea/Arabian Gulf brine
(~41–42 ppt, different ion ratios) — a striking, checkable gap. This matters concretely because
NEOM's ~$1.5–2B Oxagon brine-mining complex (Enowa/Itochu/Veolia) was quietly cancelled in May 2024
with no public explanation. The prototype: a PHREEQC (Pitzer database) multi-mineral crystallization-
sequence and value-stacking TEA parametrized on real Red Sea/Gulf brine assay data and current KSA
electricity/PV costs, computing which precipitation sequence and operating envelope would (or
wouldn't) make brine mining economical — effectively re-deriving the economics NEOM's project ran
into. Differentiator: it's the first brine-mineral TEA calibrated to actual regional chemistry rather
than generic seawater, and it directly engages a real, high-profile, unresolved Saudi industry
question rather than a hypothetical one.

**3. Cyber-Physical Resilience Co-Simulation Benchmark (G1) — Digitalisation, Automation & Smart
Water Management.** An MDPI systematic review explicitly calls out the absence of "end-to-end
detection models integrated with simulations or digital twins that capture attack dynamics, quantify
impacts... and assess contributions to overall system resilience" — current work is siloed into
IT-intrusion detection, hydraulic-anomaly detection, and mitigation research that don't talk to each
other. The prototype: an EPANET hydraulic model coupled to a synthetic SCADA/PLC attack-simulation
layer (e.g., spoofed sensor readings, valve/pump command injection) on standard benchmark networks
(Net3, C-town), quantifying detection latency, resilience degradation, and restoration cost under a
matrix of attack scenarios versus a no-attack baseline. Differentiator: it's a genuine cross-domain
synthesis (cybersecurity + hydraulic simulation) that the literature says doesn't exist yet, with
direct relevance to Saudi Arabia's single-point-of-failure exposure from desalination-dependent water
supply — a national-security-adjacent framing likely to resonate with a state-backed prize.

**4. Sensor-Free NRW Estimation via Cross-Utility Benchmarking (E2) — Water Efficiency, Conservation
& Consumption Management.** Most non-revenue-water (NRW) tooling assumes real-time sensor networks;
NWC/SWA has historically reported NRW above 25–30% in parts of the Saudi network, and many utilities
worldwide report only billing and production volumes (e.g., IBNET-style public data) with no field
sensors at all. The prototype: an explainable ML model that estimates NRW purely from billing,
network-age, and climate features, validated via leave-one-utility-out cross-validation against
utilities' actually-reported NRW figures, benchmarked against a naive regression baseline.
Differentiator: unlike every commercial leak-detection product (ASTERRA, WINT, TaKaDu, Fido Tech),
it requires **zero new infrastructure or sensors** — a genuinely deployable, near-zero-marginal-cost
tool that scores strongly on GPIW's "Scalability & Feasibility" criterion specifically because it
needs no hardware, supply chain, or field access to work.

**5. Climate-Adapted Constructed-Wetland Design Optimizer (W1) — Accessible & Cost-Effective
Wastewater Solutions.** Constructed wetlands are the lowest-cost decentralized treatment option for
underserved/rural communities, but the literature explicitly flags that "evidence remains
fragmented... limits comparability and weakens direct translation to design guidance" for hot/arid
climates, where evapotranspiration-driven salt concentration and clogging break assumptions baked
into standard (temperate) EPA design guidance. The prototype: a Richards-equation/reactive-transport
parametric optimizer (HYDRUS-style, open solvers) that sizes wetland cells accounting for arid-climate
ET concentration and salt buildup, benchmarked against standard temperate design guidance to quantify
the undersizing/failure risk when arid effects are ignored — directly answering "how much bigger/
different does a wetland need to be in Riyadh vs. the guidance written for temperate climates."
Differentiator: it converts a scattered set of individual arid-CW papers into a reusable, quantified
design tool, filling an explicitly-named literature gap, and serves the segment of Saudi Arabia
(rural/remote communities, off main sewer trunk) that centralized-plant vendors don't reach.

---

## 5. Recommendation

### 5.1 Provenance of this final pick

This recommendation was reached jointly with an independent parallel research effort (a separate
agent, "Codex") that ran the same GPIW research brief with no visibility into this document. That
effort converged on the same underlying landscape gap from its own independent search — CORMIX,
Visual Plumes, PLUMES2.0, and BrIHne are all steady-state/near-field-only, and the literature names
the Red Sea and Arabian Gulf as the semi-enclosed seas most exposed to cumulative brine buildup — but
proposed a different product framing (a single-plant real-time adaptive controller, "BrineGuard",
rather than this document's original basin-scale cumulative-risk map, "S1"). Reconciling the two:

- The basin-scale, open-data cumulative-dose model (this document's original contribution) was kept
  as the physics/state layer — it is the more solo-buildable, more reproducible core, since a
  simplified box/advection-diffusion transport model at basin scale is a substantially lighter lift
  than the full high-fidelity-simulation → surrogate → distributionally-robust-MPC → conformal-
  calibration pipeline the single-plant real-time controller framing would have required.
- The single-plant controller's core insight — that a passive risk *map* is weaker on Audacious
  Vision and Long-Term Viability than something that produces an actionable, quantified intervention —
  was accepted, and the design was extended from static risk mapping into an active coordination/
  dispatch optimizer.
- Codex then independently verified, via live web search rather than assumption, that "schedule
  brine discharge" is not a physically credible lever (dedicated corrosive-brine storage at the scale
  needed is reservoir-scale infrastructure, not a software assumption) and identified the literature
  showing where real SWRO operational flexibility actually lives (time-varying production with
  product water as the storage medium; variable-feed-pressure operation; potable-water storage;
  interconnection between plants). This correction was independently re-verified for this document
  (§4, item 1) before being adopted.

The result is a merged, corrected direction that neither independent effort proposed on its own.

### 5.2 Final recommendation

**Pursue coordinated multi-plant desalination production & environmental dispatch (§4, item 1),
filed under Environmental Sustainability & Water Resource Conservation.**

Reasoning, weighed against the alternatives above:

- **It has the cleanest, most independently-corroborated gap**, confirmed by two separate research
  passes run without shared context: CORMIX/Visual Plumes/PLUMES2.0/BrIHne documentation and multiple
  dispersion-modeling/environmental-impact reviews all converge on the same structural limitation
  (steady-state, near-field-only tools) and the same vulnerable geography (semi-enclosed seas, Red
  Sea/Gulf named explicitly). That's a stronger evidentiary basis than D1/Z1, which rests on
  inference from a single cancelled project with no public post-mortem.
- **It doesn't require explaining someone else's failure.** D1/Z1's narrative strength ("we solved
  what NEOM couldn't") is also its risk: a jury may reasonably ask why a $1.5–2B industrial JV walked
  away if the economics work, and a solo TEA prototype can't fully answer that. This pick's narrative
  is additive, not corrective — it fills a genuine blind spot in how desalination dispatch is
  currently planned, using operational flexibility that is independently documented to exist.
- **It is grounded in real, verified operational mechanisms, not an invented lever.** The correction
  from "brine storage/scheduling" to "production/train-count/potable-storage dispatch" was checked
  against actual literature (Ghobeity & Mitsos's time-dependent SWRO operation MINLP; Sorek's
  pressure-center variable-feed-pressure design) and against the real economics of brine storage
  (corrosion-limited, capex-dominated at the scale needed) — this avoids a first-draft flaw that
  would have undermined Technical Excellence and Durability & Safety if left uncorrected.
- **It scores best against GPIW's own criteria as a set, not just individually.** Technical Excellence
  (extends a named structural limitation of incumbent tools with a mechanism verified against real
  plant operating literature), Clear Market Need (every coastal desal cluster needs discharge
  planning, and cumulative multi-plant impact is currently invisible to that process), Life-Cycle
  Impact (directly reduces ecological exposure using flexibility that already exists, no new
  capex/hardware required), Performance Measurability (a clean three-way ablation — status quo vs.
  independent flexibility vs. coordinated dispatch — isolating exactly what coordination buys),
  Durability & Safety (constrained by real plant ramping/storage/demand limits, not an idealized
  brine buffer), and Audacious-yet-Achievable (basin-scale, multi-plant coordination framed as an
  actionable dispatch tool, buildable from open bathymetry/current data with no proprietary access).
- **It is fully reproducible from open data** — GEBCO, Copernicus Marine/HYCOM, published
  salinity-tolerance thresholds, and public plant capacity figures — with no dependency on obtaining
  real discharge-permit data from Saudi operators, which de-risks the solo-timeline execution plan.
- **Long-term viability beyond the prize is concrete**: a coordinated-dispatch tool is directly usable
  by SWA, NEOM/Red Sea Global, or a regional operator managing an interconnected plant cluster as
  operational decision support — a plausible adoption path distinct from a one-off research artifact,
  and stronger than a permitting-only map because it has an operational owner (the dispatch/planning
  desk), not just a compliance office.
- **Its scope-limiting assumption is stated explicitly, not hidden**: the prototype models a synthetic
  interconnected multi-plant coastal cluster, which is realistic for some but not all Saudi
  desalination infrastructure; this should be stated plainly in the submission rather than implied to
  hold universally.

Keep **Z1 (Gulf-brine-calibrated mineral TEA)** as the strongest backup, with one refinement from this
reconciliation process: if pursued, frame it in Codex's "BrineTrain" style — robust decision-making
under uncertain feed chemistry/price/demand that refuses to count unsold recovered product as value —
rather than this document's original framing tied specifically to explaining NEOM's cancellation,
which invites an unanswerable "why did the JV walk away then" question that a solo TEA prototype
cannot resolve.

### 5.3 Cross-check against a third, independently-run report (Gemini Deep Research)

The user separately ran Google Gemini's Deep Research on a differently-worded prompt that — unlike
this document's brief or Codex's — included the user's actual personal background (BSc Chemical
Engineering, MSc Business & Innovation, applied PyTorch experience). That report's top pick,
**NeuroDesal-PINN**, proposed a physics-informed neural network embedding solution-diffusion flux,
concentration-polarization film theory, and a unified Hermia fouling-law formulation (with adaptive
sigmoid weighting to blend the four classical fouling-mechanism regimes) into the PINN loss function,
to predict RO fouling and optimize antiscalant dosing from sparse plant sensor data — pitched
specifically as the strongest fit to the user's own ChemE/PyTorch background.

This was checked against this document's own landscape notes (§1.1: "ML-for-membrane-fouling... is
SATURATED") and against a fresh, targeted search. The result rules it out, including its sharpened
form: **Garakani & Chew (2025, *ScienceDirect*), "A physics-informed neural network for interpretable
membrane-fouling prediction with adaptive transitions between fouling mechanisms,"** already
implements essentially the same mechanism — unified Hermia formulation, adaptive sigmoid weighting
for smooth transitions between the four blocking regimes, mechanism weights learned from data via a
physics-informed loss. **Helali et al. (2025)** separately already embeds the solution-diffusion/
concentration-polarization equations into a PINN for SWRO performance monitoring, and a 2026
ScienceDirect critical review of PINNs in water/wastewater systems confirms the subfield is mature,
not an open gap. NeuroDesal-PINN's proposed R²>0.96-against-aggregated-literature-datasets validation
plan is also structurally weaker than a controlled ablation benchmark (it compares fit across
heterogeneous published experiments rather than the same method against baselines under matched
conditions, as this document's candidates and BrineGuard Coast all do).

The user's ChemE/PyTorch background is a real, legitimate factor under criterion 8 (team execution
credibility) that neither this document nor RESEARCH_CODEX.md had visibility into — but it speaks to
1 of 8 equally-weighted criteria and cannot offset a direct collision with criterion 1 (Technical
Excellence, "degree of innovation vs. state of the art") from a technical premise that is already
published, including the specific narrowed version proposed as its differentiator. **NeuroDesal-PINN
is rejected, including as a secondary/stretch application in its current form.** The final
recommendation is unchanged: coordinated multi-plant desalination production & environmental dispatch
(§5.2). The user's chemical-engineering background remains useful within that prototype — for
modeling the plant-level operating constraints (feed-pressure/recovery relationships, membrane/pump/
energy-recovery limits, water-quality/blending requirements) that feed the dispatch optimizer — rather
than as the headline technical contribution.
