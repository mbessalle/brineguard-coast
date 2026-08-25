from __future__ import annotations

import numpy as np


def audit_schedule(config: dict, production_m3_h: np.ndarray, storage_m3: np.ndarray,
                   tolerance_m3: float = 1e-6) -> dict:
    """Deterministically re-verify a schedule against every dispatch constraint.

    Independent of the optimizer: recomputes the storage recursion and checks
    bounds, terminal storage, production limits, and ramp limits directly from
    the config (BUILD_PLAN Phase 2 gate: zero water-balance violations).
    """
    cfg = config["dispatch"]
    # Audit whatever length the schedule has (a 48h window or a full rolled
    # series); the config series may be longer than the schedule.
    demand = np.asarray(cfg["demand_m3_h"][: len(production_m3_h)], dtype=float)
    tank = cfg["tank"]
    plants = cfg["plants"]
    minimum = np.array([p["min_m3_h"] for p in plants])
    maximum = np.array([p["max_m3_h"] for p in plants])
    initial = np.array([p["initial_m3_h"] for p in plants])
    ramp_limit = np.array([p["ramp_m3_h_per_h"] for p in plants])
    expected_storage = tank["initial_m3"] + np.cumsum(production_m3_h.sum(axis=1) - demand)
    steps = np.diff(production_m3_h, axis=0, prepend=initial[None, :])
    checks = {
        "storage_recursion_max_abs_error_m3": float(np.max(np.abs(storage_m3 - expected_storage))),
        "storage_below_minimum_max_m3": float(np.max(tank["minimum_m3"] - storage_m3, initial=0.0)),
        "storage_above_capacity_max_m3": float(np.max(storage_m3 - tank["capacity_m3"], initial=0.0)),
        "terminal_storage_abs_error_m3": float(abs(storage_m3[-1] - tank["terminal_m3"])),
        "production_below_minimum_max_m3_h": float(np.max(minimum[None, :] - production_m3_h, initial=0.0)),
        "production_above_maximum_max_m3_h": float(np.max(production_m3_h - maximum[None, :], initial=0.0)),
        "ramp_above_limit_max_m3_h": float(np.max(np.abs(steps) - ramp_limit[None, :], initial=0.0)),
    }
    violations = {name: value for name, value in checks.items() if value > tolerance_m3}
    return {"checks": checks, "violations": violations, "violation_count": len(violations),
            "tolerance_m3": tolerance_m3, "pass": not violations}
