from __future__ import annotations

import copy

import numpy as np
import pytest

from brineguard.config import load_config
from brineguard.dispatch.rolling import solve_rolling, verify_rolling
from brineguard.dispatch.verify import audit_schedule
from brineguard.transport.kernels import load_or_build_kernel


@pytest.fixture(scope="module")
def phase3_config():
    return load_config("configs/phase3.yaml")


@pytest.fixture(scope="module")
def phase3_result(phase3_config):
    return solve_rolling(phase3_config)


# ── Reduced fixture for faster determinism / cache tests ──────────────
@pytest.fixture(scope="module")
def reduced_config(phase3_config):
    """Phase 3 config with total=60, horizon=48, enact=12 → 2 windows."""
    cfg = copy.deepcopy(phase3_config)
    cfg["rolling"]["total_hours"] = 60
    cfg["rolling"]["enact_hours"] = 12
    # Trim demand and tariff to 60 entries
    cfg["dispatch"]["demand_m3_h"] = cfg["dispatch"]["demand_m3_h"][:60]
    cfg["dispatch"]["tariff"] = cfg["dispatch"]["tariff"][:60]
    return cfg


# ── Window count and coverage ─────────────────────────────────────────


def test_enacted_hours_equal_total_hours(phase3_config, phase3_result):
    total = phase3_config["rolling"]["total_hours"]
    assert phase3_result["production_m3_h"].shape[0] == total
    assert phase3_result["storage_m3"].shape[0] == total


def test_no_gaps_in_enacted_storage(phase3_config, phase3_result):
    demand = np.asarray(phase3_config["dispatch"]["demand_m3_h"], dtype=float)
    tank = phase3_config["dispatch"]["tank"]
    storage = phase3_result["storage_m3"]
    production = phase3_result["production_m3_h"].sum(axis=1)
    # Recompute storage recursion from enacted arrays to verify no gaps
    expected = tank["initial_m3"] + np.cumsum(production - demand)
    assert np.allclose(storage, expected, atol=1e-5)


def test_window_count(phase3_config, phase3_result):
    # 96 total, 48 horizon, 6 enact: windows at 0,6,12,18,24,30,36,42,48 = 9
    rolling = phase3_config["rolling"]
    total, horizon, enact = rolling["total_hours"], phase3_config["dispatch"]["horizon_hours"], rolling["enact_hours"]
    n_regular = (total - horizon) // enact
    # The last window starts at total_hours - horizon
    expected_windows = n_regular + 1  # +1 for the final window
    assert len(phase3_result["windows"]) == expected_windows

    # Verify start hours
    starts = [w["start_hour"] for w in phase3_result["windows"]]
    expected_starts = list(range(0, total - horizon, enact)) + [total - horizon]
    assert starts == expected_starts


def test_every_hour_covered_no_overlap(phase3_config, phase3_result):
    """Verify that each enacted hour appears exactly once (no gaps, no overlaps)."""
    enacted = phase3_result["production_m3_h"]
    total = phase3_config["rolling"]["total_hours"]
    horizon = phase3_config["dispatch"]["horizon_hours"]
    enact = phase3_config["rolling"]["enact_hours"]

    # Each window's enacted range should be contiguous and non-overlapping
    t = 0
    for w in phase3_result["windows"]:
        start = w["start_hour"]
        remaining = total - start
        if start == total - horizon:
            expected = remaining  # last window enacts all remaining
        else:
            expected = enact
        # The enacted range must cover [start, start+expected)
        t_end = start + expected
        assert t == start, f"gap at hour {t}, window starts at {start}"
        t = t_end
    assert t == total, f"last enacted hour {t} != total {total}"


# ── Full-schedule audit ───────────────────────────────────────────────


def test_full_96h_passes_audit(phase3_config, phase3_result):
    """Enacted schedule must pass audit_schedule with zero violations."""
    audit = verify_rolling(phase3_config, phase3_result)
    assert audit["pass"], audit["violations"]
    assert audit["violation_count"] == 0


def test_audit_checks_terminal_storage(phase3_config, phase3_result):
    audit = verify_rolling(phase3_config, phase3_result)
    terminal_err = audit["checks"]["terminal_storage_abs_error_m3"]
    assert terminal_err < 1e-6, f"terminal mismatch: {terminal_err}"


# ── Cross-window ramp continuity ──────────────────────────────────────


def test_cross_window_ramp_continuity(phase3_config, phase3_result):
    """|production[t] - production[t-1]| <= ramp limit at every seam hour."""
    enact = phase3_config["rolling"]["enact_hours"]
    horizon = phase3_config["dispatch"]["horizon_hours"]
    total = phase3_config["rolling"]["total_hours"]
    ramp_limits = np.array([p["ramp_m3_h_per_h"] for p in phase3_config["dispatch"]["plants"]])
    production = phase3_result["production_m3_h"]

    seam_hours = list(range(enact, total - horizon + 1, enact))
    # Also check the boundary at the first enacted hour (t=0 ramp vs initial)
    # but the real concern is cross-window seams where t and t-1 come from different windows.
    for t in seam_hours:
        step = np.abs(production[t] - production[t - 1])
        violations = step - ramp_limits
        assert np.all(violations <= 1e-6), (
            f"ramp violation at seam hour {t}: step={step}, limit={ramp_limits}"
        )


# ── Kernel cache ──────────────────────────────────────────────────────


def test_kernel_cache_hit_on_second_window(phase3_config, tmp_path):
    """Second window's load_or_build_kernel should be a cache hit."""
    rolling = phase3_config["rolling"]
    enact, total, horizon = rolling["enact_hours"], rolling["total_hours"], phase3_config["dispatch"]["horizon_hours"]
    demand_full = np.asarray(phase3_config["dispatch"]["demand_m3_h"], dtype=float)
    tariff_full = np.asarray(phase3_config["dispatch"]["tariff"], dtype=float)

    # First window (t=0)
    wcfg0 = copy.deepcopy(phase3_config)
    wcfg0["dispatch"]["demand_m3_h"] = demand_full[0:horizon].tolist()
    wcfg0["dispatch"]["tariff"] = tariff_full[0:horizon].tolist()
    kernel0, info0 = load_or_build_kernel(wcfg0, tmp_path)
    assert info0["cache_hit"] is False

    # Second window (t=enact) — same horizon, same domain → cache hit
    t = enact
    wcfg1 = copy.deepcopy(phase3_config)
    wcfg1["dispatch"]["demand_m3_h"] = demand_full[t : t + horizon].tolist()
    wcfg1["dispatch"]["tariff"] = tariff_full[t : t + horizon].tolist()
    kernel1, info1 = load_or_build_kernel(wcfg1, tmp_path)
    assert info1["cache_hit"] is True, (
        f"expected cache hit on second window, got: {info1}"
    )
    assert np.array_equal(kernel0, kernel1)


# ── Determinism ───────────────────────────────────────────────────────


def test_determinism_two_runs_identical(reduced_config):
    """Two runs with the same config give identical enacted arrays."""
    r1 = solve_rolling(reduced_config)
    r2 = solve_rolling(reduced_config)
    assert np.array_equal(r1["production_m3_h"], r2["production_m3_h"])
    assert np.array_equal(r1["storage_m3"], r2["storage_m3"])
    assert r1["energy_cost"] == r2["energy_cost"]


def test_determinism_two_runs_identical_full(phase3_config):
    """Full 96h run: two runs give identical enacted arrays."""
    r1 = solve_rolling(phase3_config)
    r2 = solve_rolling(phase3_config)
    assert np.array_equal(r1["production_m3_h"], r2["production_m3_h"])
    assert np.array_equal(r1["storage_m3"], r2["storage_m3"])
    assert r1["energy_cost"] == r2["energy_cost"]