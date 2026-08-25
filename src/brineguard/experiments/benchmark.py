from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from brineguard.config import load_config
from brineguard.dispatch.model import constant_schedule, solve_dispatch
from brineguard.dispatch.independent import solve_independent
from brineguard.dispatch.verify import audit_schedule
from brineguard.reporting.plots import coordination_benefit_figure
from brineguard.transport.kernels import load_or_build_kernel
from brineguard.transport.solver import simulate


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _sha256(config: dict) -> str:
    return hashlib.sha256(
        yaml.safe_dump(config, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _exposure_metrics(config: dict, rec: np.ndarray) -> dict:
    """Compute exposure_sum, peak_anomaly from direct receptor series."""
    receptors = config["domain"]["receptors"]
    thresholds = np.array([r["threshold_kg_m3"] for r in receptors])
    areas = np.array([r["area_m2"] for r in receptors])
    exceedance = np.maximum(rec - thresholds[None, :], 0.0)
    return {
        "exposure_sum_m2_kg_m3_h": float(np.sum(areas[None, :] * exceedance)),
        "peak_anomaly_kg_m3": float(rec.max()),
    }


def _energy_and_water(config: dict, production_m3_h: np.ndarray) -> dict:
    cfg = config["dispatch"]
    plants = cfg["plants"]
    tariff = np.asarray(cfg["tariff"][: len(production_m3_h)], dtype=float)
    energy_rates = np.array([p["energy_kwh_m3"] for p in plants])
    return {
        "energy_cost": float(np.sum(tariff[:, None] * energy_rates[None, :] * production_m3_h)),
        "water_produced_m3": float(production_m3_h.sum()),
    }


def _strategy_a(cfg_sha256: str, config: dict) -> dict:
    """Strategy A: constant schedule."""
    result = constant_schedule(config)
    audit = audit_schedule(config, result["production_m3_h"], result["storage_m3"])
    rec, _ = simulate(config, result["loads_kg_s"])
    return {
        "config_sha256": cfg_sha256,
        "strategy": "A",
        "energy_cost": result["energy_cost"],
        "water_produced_m3": float(result["production_m3_h"].sum()),
        "audit_pass": audit["pass"],
        "audit_violations": audit["violations"],
        **_exposure_metrics(config, rec),
    }


def _strategy_b(cfg_sha256: str, config: dict, kernel: np.ndarray, rule: str) -> dict:
    """Strategy B: independent dispatch (capacity or cost rule)."""
    result = solve_independent(config, kernel, rule)
    audit = audit_schedule(config, result["production_m3_h"], result["storage_m3"])
    rec, _ = simulate(config, result["loads_kg_s"])
    return {
        "config_sha256": cfg_sha256,
        "strategy": f"B_{rule}",
        "rule": rule,
        "energy_cost": result["energy_cost"],
        "water_produced_m3": float(result["production_m3_h"].sum()),
        "audit_pass": audit["pass"],
        "audit_violations": audit["violations"],
        **_exposure_metrics(config, rec),
    }


def _strategy_c(cfg_sha256: str, config: dict, kernel: np.ndarray,
                cost_cap: float | None = None) -> dict:
    """Strategy C: coordinated dispatch, optionally cost-capped."""
    result = solve_dispatch(config, kernel, cost_cap=cost_cap)
    audit = audit_schedule(config, result["production_m3_h"], result["storage_m3"])
    rec, _ = simulate(config, result["loads_kg_s"])
    prefix = "C_matched" if cost_cap is not None else "C"
    return {
        "config_sha256": cfg_sha256,
        "strategy": prefix,
        "cost_cap": cost_cap,
        "energy_cost": result["energy_cost"],
        "water_produced_m3": float(result["production_m3_h"].sum()),
        "audit_pass": audit["pass"],
        "audit_violations": audit["violations"],
        **_exposure_metrics(config, rec),
        "production_m3_h": result["production_m3_h"],
        "loads_kg_s": result["loads_kg_s"],
    }


def _pearson_correlation(a: np.ndarray, b: np.ndarray) -> float:
    """Pairwise Pearson r of plant hourly brine loads."""
    a_mean, b_mean = a.mean(axis=0), b.mean(axis=0)
    a_demean, b_demean = a - a_mean, b - b_mean
    num = (a_demean * b_demean).sum(axis=0)
    den = np.sqrt((a_demean ** 2).sum(axis=0) * (b_demean ** 2).sum(axis=0))
    with np.errstate(invalid="ignore"):
        r = np.where(den > 0, num / den, 0.0)
    return r


def _single_source_exposure(config: dict, loads_kg_s: np.ndarray,
                            source_idx: int) -> float:
    """Exposure from a single source simulated in isolation."""
    single = np.zeros_like(loads_kg_s)
    single[:, source_idx] = loads_kg_s[:, source_idx]
    rec, _ = simulate(config, single)
    return _exposure_metrics(config, rec)["exposure_sum_m2_kg_m3_h"]


def _coincidental_dumping(config: dict, b_loads: np.ndarray, c_loads: np.ndarray,
                          b_prod: np.ndarray, c_prod: np.ndarray,
                          b_result: dict, c_result: dict) -> dict:
    """Coincidental dumping metrics (BUILD_PLAN §7)."""
    n_sources = b_loads.shape[1]
    corr = _pearson_correlation(b_loads, c_loads)
    # Overlap contribution: joint exposure minus sum of single-source exposures.
    joint_exp = b_result["exposure_sum_m2_kg_m3_h"]
    single_exps = [_single_source_exposure(config, b_loads, i) for i in range(n_sources)]
    overlap_b = joint_exp - sum(single_exps)
    joint_exp_c = c_result["exposure_sum_m2_kg_m3_h"]
    single_exps_c = [_single_source_exposure(config, c_loads, i) for i in range(n_sources)]
    overlap_c = joint_exp_c - sum(single_exps_c)

    metrics: dict = {
        "pearson_r": {f"plant_{i}": float(corr[i]) for i in range(n_sources)},
        "overlap_contribution_B_m2_kg_m3_h": float(overlap_b),
        "overlap_contribution_C_m2_kg_m3_h": float(overlap_c),
        "single_source_exposures_B": [float(v) for v in single_exps],
        "single_source_exposures_C": [float(v) for v in single_exps_c],
    }

    # Tidal-specific: fraction of loads released during poor-flushing hours.
    cur = config["domain"].get("currents")
    if cur is not None and cur["type"] == "tidal":
        from brineguard.transport.solver import _current_at_time
        hours = b_loads.shape[0]
        t0_s = cur["t0_h"] * 3600.0
        dt_s = 3600.0
        poor_mask = np.zeros(hours, dtype=bool)
        for h in range(hours):
            ut, _ = _current_at_time(config, t0_s + h * dt_s)
            poor_mask[h] = abs(ut) < 0.02
        b_total = float(b_loads.sum())
        c_total = float(c_loads.sum())
        b_poor = float(b_loads[poor_mask].sum()) if poor_mask.any() else 0.0
        c_poor = float(c_loads[poor_mask].sum()) if poor_mask.any() else 0.0
        metrics["poor_flushing_fraction_B"] = b_poor / b_total if b_total > 0 else 0.0
        metrics["poor_flushing_fraction_C"] = c_poor / c_total if c_total > 0 else 0.0

    return metrics


def _apply_flex(config: dict, flex: str) -> dict | None:
    """Apply flexibility scenario deep copy; return None if infeasible."""
    cfg = copy.deepcopy(config)
    plants = cfg["dispatch"]["plants"]
    n_i, horizon = len(plants), cfg["dispatch"]["horizon_hours"]
    demand = np.asarray(cfg["dispatch"]["demand_m3_h"][:horizon], dtype=float)
    capacities = np.array([p["max_m3_h"] for p in plants])
    mean_demand = float(demand.mean())

    if flex == "flex4":
        return cfg  # Use configured min/max as-is.

    if flex in ("flex1", "flex2"):
        # Nominal = capacity-proportional share of mean demand.
        nominal = mean_demand * capacities / capacities.sum()
        if flex == "flex1":
            for i, p in enumerate(plants):
                p["min_m3_h"] = float(nominal[i])
                p["max_m3_h"] = float(nominal[i])
        else:  # flex2
            for i, p in enumerate(plants):
                p["min_m3_h"] = float(0.9 * nominal[i])
                p["max_m3_h"] = float(1.1 * nominal[i])

    # Feasibility check: ramp and terminal storage.
    tank = cfg["dispatch"]["tank"]
    total_prod = sum(p["max_m3_h"] for p in plants)
    total_min = sum(p["min_m3_h"] for p in plants)
    if total_min > max(demand) or total_prod < min(demand):
        return None  # Cannot satisfy hourly demand.
    net = demand.sum() + tank["terminal_m3"] - tank["initial_m3"]
    if net < horizon * total_min or net > horizon * total_prod:
        return None  # Terminal storage unreachable.
    # Check ramp: any plant's nominal step exceeds its ramp limit.
    for p in plants:
        if p["ramp_m3_h_per_h"] < abs(p["max_m3_h"] - p.get("initial_m3_h", (p["min_m3_h"] + p["max_m3_h"]) / 2)):
            return None
    return cfg


def run_benchmark(config_paths: list, run_id: str, output_root: str = "runs",
                  flex_scenarios: tuple = ("flex1", "flex2", "flex4")) -> Path:
    output_dir = Path(output_root) / run_id
    output_dir.mkdir(parents=True)
    (output_dir / "figures").mkdir()

    all_cells: dict = {}
    flat_rows: list[dict] = []
    strategies_to_keep = set()  # track which strategies we need for coincidental dumping

    for cpath in config_paths:
        cpath = Path(cpath).resolve()
        base_config = load_config(cpath)
        config_label = cpath.stem

        for flex in flex_scenarios:
            cell_config = _apply_flex(base_config, flex)
            cell_key = f"{config_label}/{flex}"

            if cell_config is None:
                all_cells[cell_key] = {"infeasible": True, "reason": "flex transformation violates feasibility", "config": str(cpath), "flex": flex}
                flat_rows.append({"cell": cell_key, "strategy": None, "status": "infeasible"})
                continue

            cfg_sha = _sha256(cell_config)
            kernel, _ = load_or_build_kernel(cell_config, cell_config["run"]["kernel_cache_dir"])
            cell_entry: dict = {"config": str(cpath), "flex": flex, "config_sha256": cfg_sha, "strategies": {}}

            # Strategy A
            a = _strategy_a(cfg_sha, cell_config)
            cell_entry["strategies"]["A"] = a
            flat_rows.append({"cell": cell_key, "strategy": "A", **a})

            # Strategy B — two rules
            for rule in ("capacity", "cost"):
                b = _strategy_b(cfg_sha, cell_config, kernel, rule)
                cell_entry["strategies"][f"B_{rule}"] = b
                flat_rows.append({"cell": cell_key, "strategy": f"B_{rule}", **b})

            # Strategy C (unmatched)
            c_unmatched = _strategy_c(cfg_sha, cell_config, kernel)
            cell_entry["strategies"]["C"] = c_unmatched
            flat_rows.append({"cell": cell_key, "strategy": "C", **c_unmatched})

            # Strategy C matched-cost for each B variant
            for rule in ("capacity", "cost"):
                b_key = f"B_{rule}"
                b_entry = cell_entry["strategies"][b_key]
                c_key = f"C_matched_{rule}"
                try:
                    c_matched = _strategy_c(cfg_sha, cell_config, kernel,
                                           cost_cap=b_entry["energy_cost"])
                    cell_entry["strategies"][c_key] = c_matched
                    # benefit
                    exp_b = b_entry["exposure_sum_m2_kg_m3_h"]
                    exp_c = c_matched["exposure_sum_m2_kg_m3_h"]
                    if exp_b > 0:
                        benefit = (exp_b - exp_c) / exp_b
                    else:
                        benefit = 0.0
                    cell_entry["strategies"][c_key]["coordination_benefit"] = float(benefit)
                    cell_entry["strategies"][c_key]["benefit_null"] = False
                    flat_rows.append({"cell": cell_key, "strategy": c_key,
                                      "coordination_benefit": float(benefit), **c_matched})
                except RuntimeError:
                    cell_entry["strategies"][c_key] = {
                        "config_sha256": cfg_sha, "strategy": c_key,
                        "benefit_null": True, "benefit_reason": "capped solve infeasible",
                        "cost_cap": b_entry["energy_cost"],
                    }
                    flat_rows.append({"cell": cell_key, "strategy": c_key,
                                      "status": "infeasible_capped"})

            # Coincidental dumping: B vs C for each rule
            dump = {}
            for rule in ("capacity", "cost"):
                b_key = f"B_{rule}"
                b_loads = cell_entry["strategies"][b_key].get("loads_kg_s")
                b_prod = cell_entry["strategies"][b_key].get("production_m3_h")
                c_loads = c_unmatched.get("loads_kg_s")
                c_prod = c_unmatched.get("production_m3_h")
                if b_loads is not None and c_loads is not None:
                    dump[f"B_{rule}_vs_C"] = _coincidental_dumping(
                        cell_config, b_loads, c_loads,
                        b_prod if b_prod is not None else np.zeros_like(b_loads),
                        c_prod if c_prod is not None else np.zeros_like(c_loads),
                        cell_entry["strategies"][b_key], c_unmatched,
                    )
            if dump:
                cell_entry["coincidental_dumping"] = dump

            all_cells[cell_key] = cell_entry

    # Strip heavy arrays from comparison.json (keep only metrics).
    comparison = {}
    for cell_key, cell in all_cells.items():
        if cell.get("infeasible"):
            comparison[cell_key] = cell
            continue
        clean = {"config": cell["config"], "flex": cell["flex"],
                 "config_sha256": cell["config_sha256"], "strategies": {}}
        for skey, sval in cell["strategies"].items():
            clean["strategies"][skey] = {
                k: v for k, v in sval.items()
                if k not in ("production_m3_h", "loads_kg_s")
            }
        if "coincidental_dumping" in cell:
            clean["coincidental_dumping"] = cell["coincidental_dumping"]
        comparison[cell_key] = clean

    _json(output_dir / "comparison.json", {"cells": comparison})

    # Flat CSV.
    pd.DataFrame(flat_rows).to_csv(output_dir / "comparison.csv", index=False)

    # Manifest.
    import subprocess
    git_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip() or "unknown"
    _json(output_dir / "manifest.json", {
        "run_id": run_id, "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision, "configs": [str(Path(p).resolve()) for p in config_paths],
        "flex_scenarios": list(flex_scenarios),
    })

    # Comparison figure.
    coordination_benefit_figure(output_dir)

    return output_dir