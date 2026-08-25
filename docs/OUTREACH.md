# Stakeholder outreach pack (GPIW gap 8 — send this week, latency is the risk)

Target: 5–8 conversations, at least one written statement of interest or
technical review by ~Sept 16. Personalize the two bracketed lines; keep the
rest short. All claims match docs/CLAIMS.md.

## Target list (fill names; suggested hunting grounds)

| # | Profile | Where to find | Ask |
|---|---|---|---|
| 1 | Desalination plant operations engineer (SWCC/ACWA/ENGIE IWPP, RO plant) | LinkedIn: "SWCC operations", IDA member directory | 30-min call: do plants ever shift hourly production; who would own a coordination decision? |
| 2 | Coastal/hydrodynamic modeler (consultancy: DHI, Deltares, HR Wallingford, or KAUST) | KAUST Red Sea Research Center staff pages | Technical review of the kernel approach (offer the report) |
| 3 | Marine ecologist (salinity tolerance, Red Sea coral/seagrass) | KAUST / NEOM environment team / papers citing salinity thresholds | Are threshold-based exposure proxies how you'd frame it; realistic θ values |
| 4 | Water regulator / environmental permitting (Saudi MEWA / NCEC familiarity) | LinkedIn, conference speaker lists (IDWS/IDA) | Does cumulative multi-outfall exposure appear in permitting today? |
| 5 | Water utility planner / SWA-adjacent | GPIW/IDWS ecosystem, Saudi Water Forum attendees | Would a shadow-mode advisory tool be pilotable; what data access is realistic? |
| 6 | Desalination digital/optimization vendor person (Veolia/SUEZ digital) | LinkedIn | Incumbent-workflow check (gap 23): is any cross-plant coordination done today? |

## Email A — operator / utility (asks for 30 minutes)

Subject: 30 min on how RO plants really schedule production?

Hi [NAME],

I'm a chemical engineer building BrineGuard, a computational study of whether
neighboring desalination plants could cut their combined brine impact on
sensitive coastal sites just by coordinating *when and where* water is
produced — no new hardware, same energy spend. On a benchmark system the
reduction is ~19–21%; whether that transfers to real operations depends on
questions only someone like you can answer: how much hourly flexibility RO
trains really have, and who could ever own a cross-plant scheduling decision.

Could I get 30 minutes this week or next? I'm submitting to the Saudi Water
Authority's Global Prize for Innovation in Water (Sept 30) and want the
operational reality in it, not just the math. Happy to share the technical
report; [ONE SENTENCE ON WHY THEM SPECIFICALLY].

Thanks, Moises Bessalle

## Email B — modeler / ecologist (asks for technical review)

Subject: request: poke holes in a brine-plume screening model (short review)

Hi [NAME],

I've built a screening-level model coupling desalination production
scheduling to multi-outfall salinity exposure: an analytic Gaussian-puff
source–receptor kernel (with tidal currents) cross-checked against an
independent finite-difference solver, driving a linear program that
reallocates production between plants. Headline finding: ~19–21% exposure
reduction at matched energy cost when plant–receptor geometry is
asymmetric — and a predictive bound that tells you when coordination will
NOT help, which our real-bathymetry Red Sea test confirmed.

I'd value 30–60 minutes of hostile review from someone who does this
properly: is the far-field simplification defensible for screening, and
[SPECIFIC QUESTION FOR THEM — e.g. realistic salinity thresholds for Red Sea
seagrass / whether image-source shoreline handling is acceptable]. The full
report, code, and reproduction commands are one link away. This feeds a GPIW
2026 submission (deadline Sept 30), and I'd credit the review.

Thanks, Moises Bessalle

## Email C — follow-up ask (after a good call)

Subject: one paragraph?

Hi [NAME], thank you — [ONE CONCRETE THING THEY SAID THAT CHANGED THE WORK].
If you're comfortable, a 2–3 sentence email I can quote saying the problem is
real / the approach is worth piloting (whatever you actually believe) would
materially help the submission's stakeholder-validation section. Happy to
show you exactly where and how it would appear.

## Log (fill as you go — this becomes portal evidence)

| Date | Who | Channel | Outcome | Quote/letter? |
|---|---|---|---|---|
