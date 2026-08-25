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
