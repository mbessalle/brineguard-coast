# Evidence freeze declaration (BUILD_PLAN Phase 5)

Frozen 2026-08-25T09:45Z at git 41ffc83.

The final evidence bundle is generated ONLY from these frozen inputs:
- configs/phase3.yaml (steady headline)          sha256 2b9f2c3450a8c71b…
- configs/phase3_tidal.yaml (tidal headline)     sha256 a5a1971777747dc9…
- configs/hybrid_redsea_full.yaml (representative plant scale) sha256 58db8158ed01dfb7cee45e342695829256a812a805669be62f22188048f2f298
- ensemble: 20 members, seed 20260825
- pareto: 8 points; sensitivity axes as in experiments/sensitivity.py defaults

Honesty note: development-time results for phase3/phase3_tidal WERE inspected
while building Phases 2-4 (commits are the log). This freeze binds the final
regenerated bundle: no config/seed/weight changes after this point in response
to final numbers. Any post-freeze change requires a new dated freeze entry.

## Post-freeze addendum 2026-08-25T10:46Z — audit-driven correction
Independent adversarial audit (GPT-5.6 Sol, dispatch ctx_440d47be4d5e) found the
ensemble's coordinated schedule was not cost-capped, making the benefit
distribution a non-matched claim. Fix: ensemble.py caps C at the cheaper B's
nominal energy. Regenerated as runs/phase4-ensemble-v2 (same members/seed);
corrected minima 14.5%/16.1%, all 20 members positive, cap binding. This change
was made because of a methodology flaw, NOT in response to unfavorable numbers
(the corrected numbers are marginally lower and are the ones now reported).

## Lineage clarification 2026-08-26 — header rev vs manifest rev
This freeze's header declares "Frozen at git 41ffc83" while
evidence/manifest.json records git_revision 609b5b3. That is expected, not a
discrepancy: the header captured HEAD (41ffc83) at the moment the freeze
declaration was drafted, before the freeze commit (6e67577) itself existed.
The bundle was actually generated later, at 609b5b3 (after the d28e584 audit
correction and the Phase 5 T2 generator), and committed at aacd23c. Canonical
provenance map: docs/EVIDENCE_INDEX.md.
