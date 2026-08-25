from __future__ import annotations

import numpy as np
import pyomo.environ as pyo


def load_factor_kg_s_per_m3_h(plant: dict) -> float:
    brine_m3_per_m3 = (1.0 - plant["recovery"]) / plant["recovery"]
    return brine_m3_per_m3 * plant["brine_salinity_anomaly_kg_m3"] / 3600.0


def solve_dispatch(config: dict, kernel: np.ndarray, cost_cap: float | None = None) -> dict:
    cfg = config["dispatch"]
    plants, receptors = cfg["plants"], config["domain"]["receptors"]
    n_i, n_t, n_r = len(plants), cfg["horizon_hours"], len(receptors)
    factors = np.array([load_factor_kg_s_per_m3_h(p) for p in plants])
    coefficients = kernel * factors[None, :, None, None]
    m = pyo.ConcreteModel()
    m.I, m.T, m.R = pyo.RangeSet(0, n_i - 1), pyo.RangeSet(0, n_t - 1), pyo.RangeSet(0, n_r - 1)
    m.production = pyo.Var(m.I, m.T)
    m.storage = pyo.Var(m.T)
    m.exceedance = pyo.Var(m.R, m.T, domain=pyo.NonNegativeReals)
    for i, plant in enumerate(plants):
        for t in range(n_t):
            m.production[i, t].setlb(plant["min_m3_h"])
            m.production[i, t].setub(plant["max_m3_h"])
    tank = cfg["tank"]
    for t in range(n_t):
        m.storage[t].setlb(tank["minimum_m3"])
        m.storage[t].setub(tank["capacity_m3"])
    def storage_rule(model, t):
        previous = tank["initial_m3"] if t == 0 else model.storage[t - 1]
        return model.storage[t] == previous + sum(model.production[i, t] for i in model.I) - cfg["demand_m3_h"][t]
    m.balance = pyo.Constraint(m.T, rule=storage_rule)
    m.terminal = pyo.Constraint(expr=m.storage[n_t - 1] == tank["terminal_m3"])
    # ramp[i,t] >= |P[i,t] - P[i,t-1]|; its upper bound enforces the hard ramp limit,
    # and the objective term keeps it tight at the actual step size.
    m.ramp = pyo.Var(m.I, m.T, domain=pyo.NonNegativeReals)
    for i, plant in enumerate(plants):
        for t in range(n_t):
            m.ramp[i, t].setub(plant["ramp_m3_h_per_h"])
    def previous_production(model, i, t):
        return plants[i]["initial_m3_h"] if t == 0 else model.production[i, t - 1]
    m.ramp_up = pyo.Constraint(m.I, m.T, rule=lambda model, i, t:
                               model.ramp[i, t] >= model.production[i, t] - previous_production(model, i, t))
    m.ramp_down = pyo.Constraint(m.I, m.T, rule=lambda model, i, t:
                                 model.ramp[i, t] >= previous_production(model, i, t) - model.production[i, t])
    def exposure_rule(model, r, t):
        predicted = sum(coefficients[r, i, t, tau] * model.production[i, tau]
                        for i in range(n_i) for tau in range(t + 1))
        return model.exceedance[r, t] >= predicted - receptors[r]["threshold_kg_m3"]
    m.exposure = pyo.Constraint(m.R, m.T, rule=exposure_rule)
    energy_expr = sum(cfg["tariff"][t] * plants[i]["energy_kwh_m3"] * m.production[i, t]
                      for i in range(n_i) for t in range(n_t))
    if cost_cap is not None:
        m.cost_cap = pyo.Constraint(expr=energy_expr <= cost_cap)
    ramp_cost = cfg["ramp_weight"] * sum(m.ramp[i, t] for i in range(n_i) for t in range(n_t))
    exposure = sum(receptors[r]["area_m2"] * m.exceedance[r, t] for r in range(n_r) for t in range(n_t))
    m.objective = pyo.Objective(expr=energy_expr + ramp_cost + cfg["exposure_weight"] * exposure)
    result = pyo.SolverFactory("appsi_highs").solve(m)
    if result.solver.termination_condition != pyo.TerminationCondition.optimal:
        raise RuntimeError(f"HiGHS did not find an optimum: {result.solver.termination_condition}")
    production = np.array([[pyo.value(m.production[i, t]) for i in range(n_i)] for t in range(n_t)])
    storage = np.array([pyo.value(m.storage[t]) for t in range(n_t)])
    return {
        "production_m3_h": production, "storage_m3": storage,
        "loads_kg_s": production * factors[None, :],
        "objective": float(pyo.value(m.objective)),
        "energy_cost": float(pyo.value(energy_expr)), "ramp_cost": float(pyo.value(ramp_cost)),
        "exposure_proxy": float(pyo.value(exposure)),
        "termination_condition": str(result.solver.termination_condition), "solver": "HiGHS via Pyomo appsi",
    }


def constant_schedule(config: dict) -> dict:
    """Strategy A baseline (BUILD_PLAN §7): capacity-proportional constant production
    sized so horizon demand and the terminal-storage condition are met exactly.
    Feasibility is judged by the same `verify.audit_schedule` used for optimized runs."""
    cfg = config["dispatch"]
    demand = np.asarray(cfg["demand_m3_h"], dtype=float)
    tank, plants, hours = cfg["tank"], cfg["plants"], cfg["horizon_hours"]
    capacities = np.array([p["max_m3_h"] for p in plants])
    total_rate = (demand.sum() + tank["terminal_m3"] - tank["initial_m3"]) / hours
    production = np.tile(total_rate * capacities / capacities.sum(), (hours, 1))
    storage = tank["initial_m3"] + np.cumsum(production.sum(axis=1) - demand)
    factors = np.array([load_factor_kg_s_per_m3_h(p) for p in plants])
    tariff = np.asarray(cfg["tariff"], dtype=float)
    energy_rates = np.array([p["energy_kwh_m3"] for p in plants])
    return {
        "production_m3_h": production, "storage_m3": storage,
        "loads_kg_s": production * factors[None, :],
        "energy_cost": float(np.sum(tariff[:, None] * energy_rates[None, :] * production)),
    }
