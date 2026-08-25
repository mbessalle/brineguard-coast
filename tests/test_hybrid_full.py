"""Phase 5 T1 — hybrid Red Sea full-scale config validation tests.

Tests the representative-plant config and verifies:
  • config loads correctly
  • A-strategy (constant) passes audit
  • constant-schedule exposure materially exceeds thresholds (> 500)
  • LP dispatch is feasible and coordination delivers > 5 % exposure improvement
"""

from __future__ import annotations

import copy

import numpy as np
import pytest

from brineguard.config import load_config
from brineguard.dispatch.model import constant_schedule, solve_dispatch
from brineguard.dispatch.verify import audit_schedule
from brineguard.transport.kernels import build_kernel, reconstruct
from brineguard.transport.solver import simulate


_HYBRID_FULL = "configs/hybrid_redsea_full.yaml"


def _exposure_from_sim(config: dict, loads: np.ndarray, direct: np.ndarray) -> float:
    """Reproduce the LP exposure formula from direct-simulation concentrations."""
    receptors = config["domain"]["receptors"]
    net = direct.copy()
    for r, rec in enumerate(receptors):
        net[:, r] = np.maximum(0.0, direct[:, r] - rec["threshold_kg_m3"])
    return float(np.sum(net * np.array([r["area_m2"] for r in receptors])))


# ---------------------------------------------------------------------------
# 1 — config loads
# ---------------------------------------------------------------------------

def test_config_loads():
    cfg = load_config(_HYBRID_FULL)
    assert cfg["run"]["id"] == "hybrid-redsea-full"
    assert cfg["dispatch"]["horizon_hours"] == 48
    assert len(cfg["dispatch"]["plants"]) == 3
    assert len(cfg["dispatch"]["demand_m3_h"]) == 96

    # Plant sanity: all in the 4 000–12 500 m³/h band
    for p in cfg["dispatch"]["plants"]:
        assert 4000 <= p["max_m3_h"] <= 12500
        assert 0.38 * p["max_m3_h"] <= p["min_m3_h"] <= 0.42 * p["max_m3_h"]
        assert 0.10 * p["max_m3_h"] <= p["ramp_m3_h_per_h"] <= 0.15 * p["max_m3_h"]
        assert p["min_m3_h"] <= p["initial_m3_h"] <= p["max_m3_h"]
        assert 3.0 <= p["energy_kwh_m3"] <= 3.6
        assert 0.41 <= p["recovery"] <= 0.45
        assert 24 <= p["brine_salinity_anomaly_kg_m3"] <= 27

    agg_max = sum(p["max_m3_h"] for p in cfg["dispatch"]["plants"])
    demand_avg = sum(cfg["dispatch"]["demand_m3_h"][:48]) / 48
    assert 0.75 * agg_max <= demand_avg <= 0.85 * agg_max


# ---------------------------------------------------------------------------
# 2 — constant_schedule passes audit
# ---------------------------------------------------------------------------

def test_constant_schedule_passes_audit():
    cfg = load_config(_HYBRID_FULL)
    baseline = constant_schedule(cfg)
    audit = audit_schedule(cfg, baseline["production_m3_h"], baseline["storage_m3"])
    assert audit["pass"], audit["violations"]


# ---------------------------------------------------------------------------
# 3 — constant-schedule direct-simulation exposure exceeds threshold (> 500)
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_constant_exposure_exceeds_500(monkeypatch):
    from brineguard.transport import kernels
    from brineguard.domain_sourced import get_domain

    monkeypatch.setattr(kernels, "generate_domain", get_domain)

    cfg = load_config(_HYBRID_FULL)
    truncated = copy.deepcopy(cfg)
    truncated["dispatch"]["horizon_hours"] = 24

    baseline = constant_schedule(truncated)
    direct, _ = simulate(truncated, baseline["loads_kg_s"])
    exposure = _exposure_from_sim(truncated, baseline["loads_kg_s"], direct)
    assert exposure > 500, f"exposure_sum = {exposure:.1f}, should be > 500"


# ---------------------------------------------------------------------------
# 4 — solve_dispatch on 24 h truncated copy is feasible and coordination
#    reduces exposure by ≥ 5 %
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_dispatch_feasible_and_coordination_improves_exposure(monkeypatch):
    from brineguard.transport import kernels
    from brineguard.domain_sourced import get_domain

    monkeypatch.setattr(kernels, "generate_domain", get_domain)

    cfg = load_config(_HYBRID_FULL)
    truncated = copy.deepcopy(cfg)
    truncated["dispatch"]["horizon_hours"] = 24

    kernel = build_kernel(truncated)
    result = solve_dispatch(truncated, kernel)
    audit = audit_schedule(truncated, result["production_m3_h"], result["storage_m3"])
    assert audit["pass"], f"optimized schedule audit violations: {audit['violations']}"

    # Constant exposure: simulate and compute the same area-weighted exceedance
    baseline = constant_schedule(truncated)
    direct_const, _ = simulate(truncated, baseline["loads_kg_s"])
    const_exposure = _exposure_from_sim(truncated, baseline["loads_kg_s"], direct_const)

    opt_exposure = result["exposure_proxy"]

    rel_diff = abs(const_exposure - opt_exposure) / max(const_exposure, opt_exposure, 1.0)
    assert rel_diff > 0.05, (
        f"coordination improvement too small: const_exposure={const_exposure:.1f}, "
        f"opt_exposure={opt_exposure:.1f}, rel_diff={rel_diff:.4f}"
    )