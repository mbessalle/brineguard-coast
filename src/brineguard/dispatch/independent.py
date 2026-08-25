from __future__ import annotations

import copy

import numpy as np
import pyomo.environ as pyo

from brineguard.dispatch.model import load_factor_kg_s_per_m3_h, solve_dispatch
from brineguard.transport.kernels import build_kernel


def allocate(config: dict, rule: str) -> dict:
    """Pre-allocate per-plant hourly production obligation and storage share.

    BUILD_PLAN §7 Strategy B: two fair allocation rules.
    """
    plants = config["dispatch"]["plants"]
    n_i, n_t = len(plants), config["dispatch"]["horizon_hours"]
    demand = np.asarray(config["dispatch"]["demand_m3_h"][:n_t], dtype=float)

    if rule == "capacity":
        capacities = np.array([p["max_m3_h"] for p in plants])
        shares = capacities / capacities.sum()
        obligation = np.outer(demand, shares)
        storage_share = shares.copy()
    elif rule == "cost":
        # Baseline-cost-minimizing allocation: solve the joint dispatch with
        # exposure_weight=0 and use each plant's optimal production pattern —
        # normalized per hour so obligations sum to demand[t] (the joint solve
        # may use storage, so raw productions do not sum to demand hour-by-hour).
        # Storage share is proportional to total production.
        cost_config = copy.deepcopy(config)
        cost_config["dispatch"]["exposure_weight"] = 0.0
        kernel = build_kernel(cost_config)
        solution = solve_dispatch(cost_config, kernel)
        raw = solution["production_m3_h"]
        hourly_sum = raw.sum(axis=1)
        with np.errstate(invalid="ignore"):
            obligation = raw * (demand / hourly_sum)[:, None]
        # If any hour has zero total production, fall back to uniform split.
        zero_mask = hourly_sum == 0
        if zero_mask.any():
            obligation[zero_mask, :] = demand[zero_mask, None] / n_i
        totals = obligation.sum(axis=0)
        storage_share = totals / totals.sum() if totals.sum() > 0 else np.ones(n_i) / n_i
    else:
        raise ValueError(f"Unknown allocation rule: {rule}")

    return {
        "obligation_m3_h": obligation,       # (hours, n_plants)
        "storage_share": storage_share,      # (n_plants,)  sums to 1
        "rule": rule,
    }


def solve_independent(config: dict, kernel: np.ndarray, rule: str) -> dict:
    """Strategy B: each plant solves its own single-plant LP, then combine.

    BUILD_PLAN §7: each plant minimizes its own energy cost + ramp + exposure
    at its *local* receptors only — it does not see other plants' contributions.
    """
    cfg = config["dispatch"]
    plants, receptors = cfg["plants"], config["domain"]["receptors"]
    n_i, n_t = len(plants), cfg["horizon_hours"]
    all_receptor_names = [r["name"] for r in receptors]

    alloc = allocate(config, rule)
    obligation = alloc["obligation_m3_h"]
    storage_share = alloc["storage_share"]
    factors = np.array([load_factor_kg_s_per_m3_h(p) for p in plants])

    production_all = np.zeros((n_t, n_i))
    storage_all = np.zeros((n_t, n_i))
    per_plant = []
    total_objective = 0.0
    total_energy = 0.0
    total_ramp = 0.0
    total_exposure = 0.0

    for i, plant in enumerate(plants):
        plant_obligation = obligation[:, i]
        share = float(storage_share[i])
        tank = cfg["tank"]

        m = pyo.ConcreteModel()
        m.T = pyo.RangeSet(0, n_t - 1)
        m.production = pyo.Var(m.T)
        m.storage = pyo.Var(m.T)

        for t in range(n_t):
            m.production[t].setlb(plant["min_m3_h"])
            m.production[t].setub(plant["max_m3_h"])
            m.storage[t].setlb(tank["minimum_m3"] * share)
            m.storage[t].setub(tank["capacity_m3"] * share)

        def storage_rule(model, t):
            prev = tank["initial_m3"] * share if t == 0 else model.storage[t - 1]
            return model.storage[t] == prev + model.production[t] - plant_obligation[t]

        m.balance = pyo.Constraint(m.T, rule=storage_rule)
        m.terminal = pyo.Constraint(expr=m.storage[n_t - 1] == tank["terminal_m3"] * share)

        m.ramp = pyo.Var(m.T, domain=pyo.NonNegativeReals)
        for t in range(n_t):
            m.ramp[t].setub(plant["ramp_m3_h_per_h"])

        def prev_production(model, t):
            return plant["initial_m3_h"] if t == 0 else model.production[t - 1]

        m.ramp_up = pyo.Constraint(m.T, rule=lambda model, t:
                                   model.ramp[t] >= model.production[t] - prev_production(model, t))
        m.ramp_down = pyo.Constraint(m.T, rule=lambda model, t:
                                     model.ramp[t] >= prev_production(model, t) - model.production[t])

        # Exposure at local receptors only — plant only sees its own source column.
        local_names = plant.get("local_receptors", [])
        local_indices = [all_receptor_names.index(n) for n in local_names if n in all_receptor_names]
        if local_indices:
            m.R = pyo.RangeSet(0, len(local_indices) - 1)
            m.exceedance = pyo.Var(m.R, m.T, domain=pyo.NonNegativeReals)

            def exposure_rule(model, r_local, t):
                global_r = local_indices[r_local]
                predicted = sum(
                    kernel[global_r, i, t, tau] * factors[i] * model.production[tau]
                    for tau in range(t + 1)
                )
                return model.exceedance[r_local, t] >= predicted - receptors[global_r]["threshold_kg_m3"]

            m.exposure = pyo.Constraint(m.R, m.T, rule=exposure_rule)

            exposure_term = sum(
                receptors[local_indices[rr]]["area_m2"] * m.exceedance[rr, t]
                for rr in range(len(local_indices)) for t in range(n_t)
            )
        else:
            exposure_term = 0.0

        energy = sum(
            cfg["tariff"][t] * plant["energy_kwh_m3"] * m.production[t]
            for t in range(n_t)
        )
        ramp_cost = cfg["ramp_weight"] * sum(m.ramp[t] for t in range(n_t))

        obj = energy + ramp_cost
        if local_indices:
            obj += cfg["exposure_weight"] * exposure_term
        m.objective = pyo.Objective(expr=obj)

        result = pyo.SolverFactory("appsi_highs").solve(m)
        if result.solver.termination_condition != pyo.TerminationCondition.optimal:
            raise RuntimeError(
                f"HiGHS did not find an optimum for plant {i} ({plant['name']}): "
                f"{result.solver.termination_condition}"
            )

        prod_i = np.array([pyo.value(m.production[t]) for t in range(n_t)])
        stor_i = np.array([pyo.value(m.storage[t]) for t in range(n_t)])
        exposure_val = float(pyo.value(exposure_term)) if local_indices else 0.0

        production_all[:, i] = prod_i
        storage_all[:, i] = stor_i

        per_plant.append({
            "index": i,
            "name": plant["name"],
            "production_m3_h": prod_i,
            "storage_m3": stor_i,
            "objective": float(pyo.value(obj)),
            "energy_cost": float(pyo.value(energy)),
            "ramp_cost": float(pyo.value(ramp_cost)),
            "exposure_proxy": exposure_val,
            "storage_share": share,
        })

        total_objective += float(pyo.value(obj))
        total_energy += float(pyo.value(energy))
        total_ramp += float(pyo.value(ramp_cost))
        total_exposure += exposure_val

    aggregate_storage = storage_all.sum(axis=1)
    loads_kg_s = production_all * factors[None, :]

    return {
        "production_m3_h": production_all,
        "storage_m3": aggregate_storage,
        "loads_kg_s": loads_kg_s,
        "objective": total_objective,
        "energy_cost": total_energy,
        "ramp_cost": total_ramp,
        "exposure_proxy": total_exposure,
        "rule": rule,
        "per_plant": per_plant,
    }