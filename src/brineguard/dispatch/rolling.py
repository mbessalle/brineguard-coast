from __future__ import annotations

import copy

import numpy as np

from brineguard.dispatch.model import load_factor_kg_s_per_m3_h, solve_dispatch
from brineguard.dispatch.verify import audit_schedule
from brineguard.transport.kernels import load_or_build_kernel


def _full_series_config(config: dict) -> dict:
    """Build a config view spanning the full total_hours for audit verification."""
    cfg = copy.deepcopy(config)
    total = config["rolling"]["total_hours"]
    cfg["dispatch"]["horizon_hours"] = total
    return cfg


def solve_rolling(config: dict) -> dict:
    """Rolling-horizon dispatch driver (BUILD_PLAN §6.5).

    Decomposes a long dispatch period into overlapping windows, solves each
    window independently, and enacts the first few hours per window. Returns
    the concatenated enacted schedule plus per-window records and totals.
    """
    rolling = config["rolling"]
    enact = rolling["enact_hours"]
    total = rolling["total_hours"]
    horizon = config["dispatch"]["horizon_hours"]
    kernel_cache = config["run"]["kernel_cache_dir"]

    demand_full = np.asarray(config["dispatch"]["demand_m3_h"], dtype=float)
    tariff_full = np.asarray(config["dispatch"]["tariff"], dtype=float)
    plants = config["dispatch"]["plants"]
    n_plants = len(plants)
    factors = np.array([load_factor_kg_s_per_m3_h(p) for p in plants])

    # Accumulators for the enacted schedule
    enacted_production = np.empty((total, n_plants))
    enacted_storage = np.empty(total)
    window_records = []

    # State carried across windows
    storage_state = config["dispatch"]["tank"]["initial_m3"]
    prod_state = np.array([p["initial_m3_h"] for p in plants])

    t = 0
    while t < total:
        # Last window starts at total_hours - horizon; enact everything remaining
        if t == total - horizon or t + horizon > total:
            enacted_len = total - t
        else:
            enacted_len = enact

        # Build window config (deep copy with sliced demand/tariff)
        wcfg = copy.deepcopy(config)
        wcfg["dispatch"]["demand_m3_h"] = demand_full[t : t + horizon].tolist()
        wcfg["dispatch"]["tariff"] = tariff_full[t : t + horizon].tolist()
        wcfg["dispatch"]["tank"]["initial_m3"] = float(storage_state)
        for i in range(n_plants):
            wcfg["dispatch"]["plants"][i]["initial_m3_h"] = float(prod_state[i])

        kernel, _ = load_or_build_kernel(wcfg, kernel_cache)
        solution = solve_dispatch(wcfg, kernel)

        enacted_production[t : t + enacted_len] = solution["production_m3_h"][:enacted_len]
        enacted_storage[t : t + enacted_len] = solution["storage_m3"][:enacted_len]

        window_records.append({
            "start_hour": t,
            "objective": solution["objective"],
            "termination_condition": solution["termination_condition"],
        })

        storage_state = solution["storage_m3"][enacted_len - 1]
        prod_state = solution["production_m3_h"][enacted_len - 1]

        t += enacted_len

    # Energy cost computed directly from enacted schedule (tariff × energy_kwh_m3)
    energy_kwh = np.array([[p["energy_kwh_m3"] for p in plants]])
    energy_cost = float(np.sum(tariff_full[:, None] * energy_kwh * enacted_production))

    loads_kg_s = enacted_production * factors[None, :]

    return {
        "production_m3_h": enacted_production,
        "storage_m3": enacted_storage,
        "loads_kg_s": loads_kg_s,
        "energy_cost": energy_cost,
        "windows": window_records,
    }


def verify_rolling(config: dict, result: dict) -> dict:
    """Run audit_schedule on the full enacted schedule against the full-series config."""
    full_cfg = _full_series_config(config)
    return audit_schedule(full_cfg, result["production_m3_h"], result["storage_m3"])