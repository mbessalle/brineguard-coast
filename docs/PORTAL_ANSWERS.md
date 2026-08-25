# GPIW portal response matrix (gpiw.net — paste-ready)

Answers are claims-bounded (docs/CLAIMS.md) and character-counted with a
safety margin. Status: ☐ pending user paste of section, ☑ drafted, ✔ entered
in portal. Copy verbatim; do not improvise past the wording.

## Section 2 — Innovation Overview ✔ ENTERED in portal 2026-08-26 (draft saved; 2.6=Other/'Ennomotive open-innovation platform')

**2.1 Innovation / Project Name** (75/150):
> BrineGuard Coast — coordinated desalination dispatch for coastal protection

**2.2 TRL:** select **TRL 3** (proof of concept demonstrated computationally —
per Track A guidance "simulations, models…"; do NOT select higher).

**2.3 Award Category:** RECOMMEND **4 — Digitalization, Automation & Smart
Water Management** ("data-driven innovations improving the… optimization or
management of water systems" is literally what this is; jurors there
understand optimization evidence). Defensible alternative: 5 — Environmental
Sustainability (the outcome). One category only; decision is the applicant's —
if unsure, ask via the portal/Ennomotive Q&A whether digital-core tools belong
in 4. Audit gap 17 discussion applies.

**2.4 Innovation Summary** (1075/1100):
> BrineGuard Coast is decision-support software that reduces the marine impact of desalination without new hardware, by coordinating when and where neighboring plants produce water. Brine discharge is locked to production; today each plant schedules alone, so plumes overlap at shared sensitive sites. BrineGuard couples a linear source-receptor transport model of the coast (an analytic Gaussian-puff kernel with tidal currents, cross-validated against an independent finite-difference solver) to a linear-programming dispatch that meets water demand, storage, and ramp constraints. On a three-plant benchmark it cuts cumulative salinity exposure at protected sites by 19-21% at no extra energy cost — verified across 20 held-out current-forecast scenarios (worst case +14.5%), always re-simulated through the independent transport model, never scored by the optimizer itself. It also predicts, before deployment, whether a coastline's geometry makes coordination worthwhile — shown on real Red Sea bathymetry. Every number is reproducible from pinned inputs with one command.

**2.5 Water challenge & who is affected** (1045/1100):
> Desalination supplies most drinking water in the Gulf and is expanding worldwide; every cubic meter produced returns roughly 1.2 cubic meters of concentrated brine to the sea. Where several large plants share one coastline — as on Saudi Arabia's Red Sea and Gulf coasts — their plumes accumulate at the same reefs, seagrass meadows and nursery habitats, whose salinity tolerance is finite. Three groups carry this challenge. Coastal marine ecosystems, and the fisheries and communities that depend on them, absorb the cumulative exposure. Water authorities and plant operators must expand production for water security while meeting tightening environmental expectations — yet no operational tool manages cumulative multi-plant exposure: permits treat each outfall alone, and no plant schedules production with the sea in mind. Regulators lack a quantitative basis to require coordination. BrineGuard addresses exactly that gap: an auditable, screening-level way to reduce combined exposure using operational flexibility the plants already have.

**2.6 How did you hear about GPIW:** Ennomotive open-innovation platform
(select the closest option; free-text: "Ennomotive challenge listing").

## Section 1 — Applicant Information ☐ (paste fields; mostly personal data —
name, contact, country, organization "Individual innovator / independent")

## Section 3 — Technical Questions ☐ (paste — the highest-stakes section)

## Section 4 — Impact & Market ☐

## Section 5 — Team & Organizational Maturity ☐ (needs your funding history,
milestones — see audit gap 28)

## Section 6 — Supporting Materials ☐ (deck PDF, video, evidence ZIP — in
production)


## Section 3 — Technical Questions (in progress)

**3.1 Core principle** ✔ FINAL v2 (2142/2200; v1 was Sol-agreed, v2 incorporates
an external density-physics review the user obtained: passive-tracer claim now
conditioned on far-field + small-anomaly + prescribed currents; dense-jet
non-resolution stated; LP qualified with continuous-turndown/no-binaries fact
verified in src/brineguard/dispatch/model.py; verification-vs-validation
distinction made explicit with density-aware validation named as pathway step;
Red Sea claim scoped to "in our experiments"):
> Beyond the near-field mixing zone, and where salinity anomalies are small enough that their feedback on coastal circulation can be neglected, excess salinity can be approximated as a passive tracer carried by a prescribed current field. Under that approximation its transport is linear: doubling a discharge doubles the modeled anomaly, and anomalies from multiple discharges add. The dense near-field jet is not resolved. The model works with the diluted far-field anomaly.
>
> This linearity lets us compute the coast's response once and reuse it. For each outfall and each hour of release, we precompute the salinity anomaly arriving at every protected site. This response table is the kernel. It uses closed-form Gaussian solutions, with an idealized reflecting shoreline and prescribed tidal currents treated analytically.
>
> Brine release is fixed by water production through the recovery ratio. Choosing production schedules therefore determines exposure, which is a linear function of those schedules. The problem becomes a linear program: meet water demand and respect tank levels, turndown ranges, and ramp rates while minimizing energy cost plus exposure. Plants operate continuously within their turndown ranges, so no on-off decisions are needed and the program stays linear. The solver finds the global optimum of that program, in seconds at our benchmark scale.
>
> We check the implementation with a separate finite-difference solver that simulates the same equations by a different numerical method. The two models must agree, mass balance must close, and every schedule is scored by re-simulation rather than by the optimizer that produced it. This verifies the code, not the physics. Validating the passive-tracer approximation itself against a density-aware hydrodynamic model and field data is the first step of our pathway from proof of concept to pilot.
>
> The kernel also yields a screening test. Coordination pays only where plants differ in dose per cubic meter produced and have room to shift production. Both conditions are computable before deployment, and in our experiments the prediction held on real Red Sea bathymetry.

**Sol review recipe (fast, ~20s):** `pi --provider openai-codex --model gpt-5.6-sol --thinking low --no-extensions -p --no-session --no-tools "<prompt>"` (allowlisted, no permission wall).

**Operating mode (user-mandated):** user pastes question -> ONE short message back with final text + char count, code-verified, contract style (no em dashes, no semicolons), claims-bounded per docs/CLAIMS.md. Sol review folded into same turn only for technical-risk answers.
