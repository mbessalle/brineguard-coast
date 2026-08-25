"""Phase 4 T2: sensitivity sweeps and the cost-exposure Pareto frontier.

Pure data producers (BUILD_PLAN 6.4): the trade-off between operating cost and
salinity-exposure proxy is reported as a Pareto curve, never hidden in a single
`exposure_weight`. No figures and no disk writes here — the reporting
integration owns plotting; these functions return tidy records only.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from brineguard.config import load_config
from brineguard.dispatch.model import solve_dispatch
from brineguard.reporting.plots import pareto_frontier_figure, sensitivity_benefit_figure
from brineguard.transport.kernels import load_or_build_kernel

from brineguard.experiments.benchmark import (
    _json,
    _sha256,
    _strategy_b,
    _strategy_c,
)


def pareto_frontier(config: dict, kernel: np.ndarray, n_points: int = 8) -> list[dict]:
    """Sweep `cost_cap` from the unconstrained C energy cost down to the pure
    cost-minimum floor (exposure_weight=0), re-simulating each schedule through
    the direct solver for true exposure. Infeasible caps are recorded honestly.
    """
    unconstrained = solve_dispatch(config, kernel)
    upper = unconstrained["energy_cost"]
    cost_config = copy.deepcopy(config)
    cost_config["dispatch"]["exposure_weight"] = 0.0
    floor = solve_dispatch(cost_config, kernel)["energy_cost"]
    sha = _sha256(config)
    caps = np.linspace(float(upper), float(floor), n_points)
    frontier: list[dict] = []
    for cap in caps:
        try:
            c = _strategy_c(sha, config, kernel, cost_cap=float(cap))
            frontier.append({
                "cost_cap": float(cap),
                "energy_cost": c["energy_cost"],
                "exposure_sum": c["exposure_sum_m2_kg_m3_h"],
                "feasible": True,
            })
        except RuntimeError:
            frontier.append({"cost_cap": float(cap), "energy_cost": None,
                             "exposure_sum": None, "feasible": False})
    return frontier


def _storage_scale_config(config: dict, factor: float) -> dict:
    """Scale tank capacity and keep minimum/initial/terminal proportionally
    consistent so the operating envelope stays the same relative buffer."""
    cfg = copy.deepcopy(config)
    tank = cfg["dispatch"]["tank"]
    for key in ("initial_m3", "minimum_m3", "capacity_m3", "terminal_m3"):
        tank[key] = float(tank[key] * factor)
    return cfg


def _turndown_config(config: dict, fraction: float) -> dict:
    """Turndown tightness like the benchmark's flex2 transform: a ±fraction band
    around the capacity-proportional share of mean demand."""
    cfg = copy.deepcopy(config)
    plants = cfg["dispatch"]["plants"]
    horizon = cfg["dispatch"]["horizon_hours"]
    demand = np.asarray(cfg["dispatch"]["demand_m3_h"][:horizon], dtype=float)
    capacities = np.array([p["max_m3_h"] for p in plants])
    nominal = float(demand.mean()) * capacities / capacities.sum()
    for i, p in enumerate(plants):
        p["min_m3_h"] = float((1.0 - fraction) * nominal[i])
        p["max_m3_h"] = float((1.0 + fraction) * nominal[i])
    return cfg


def _dispersion_config(config: dict, factor: float) -> dict:
    """Scale dispersion_m2_s; changes the kernel, so it must be rebuilt."""
    cfg = copy.deepcopy(config)
    cfg["domain"]["dispersion_m2_s"] = float(cfg["domain"]["dispersion_m2_s"] * factor)
    return cfg


def _axis_record(axis: str, value: float, config: dict, cache_dir: str,
                 kernel_builder) -> dict:
    """B_capacity vs cost-matched C coordination benefit for one axis point."""
    kernel, _ = kernel_builder(config, cache_dir)
    sha = _sha256(config)
    try:
        b = _strategy_b(sha, config, kernel, "capacity")
        c = _strategy_c(sha, config, kernel, cost_cap=b["energy_cost"])
    except RuntimeError:
        return {"axis": axis, "value": value, "benefit": None, "exposure_B": None,
                "exposure_C": None, "energy_cost_B": None, "feasible": False}
    exp_b = b["exposure_sum_m2_kg_m3_h"]
    exp_c = c["exposure_sum_m2_kg_m3_h"]
    benefit = (exp_b - exp_c) / exp_b if exp_b > 0 else 0.0
    return {"axis": axis, "value": value, "benefit": float(benefit),
            "exposure_B": exp_b, "exposure_C": exp_c,
            "energy_cost_B": b["energy_cost"], "feasible": True}


def sensitivity_sweep(config: dict, kernel_builder=load_or_build_kernel, *,
                      storage_scales: tuple = (0.5, 1.0, 1.5, 2.0),
                      turndowns: tuple = (0.05, 0.10, 0.20),
                      dispersion_scales: tuple = (0.5, 1.0, 2.0)) -> list[dict]:
    """One-at-a-time sensitivity from nominal (nominal included) over three axes:
    storage capacity scale, turndown tightness, and dispersion scale. Each point
    reports the B_capacity vs cost-matched C coordination benefit. The kernel is
    rebuilt via `kernel_builder` per point so the dispersion axis (which changes
    transport) gets a fresh, content-addressed kernel.
    """
    cache_dir = config["run"]["kernel_cache_dir"]
    records: list[dict] = []
    for factor in storage_scales:
        records.append(_axis_record("storage_scale", factor,
                                    _storage_scale_config(config, factor),
                                    cache_dir, kernel_builder))
    for fraction in turndowns:
        records.append(_axis_record("turndown", fraction,
                                    _turndown_config(config, fraction),
                                    cache_dir, kernel_builder))
    for factor in dispersion_scales:
        records.append(_axis_record("dispersion_scale", factor,
                                    _dispersion_config(config, factor),
                                    cache_dir, kernel_builder))
    return records


def run_sensitivity(config_path: str | Path, run_id: str | None, *,
                    n_points: int = 8, output_root: str = "runs") -> Path:
    """CLI integration: Pareto frontier + sensitivity sweep -> JSON + figures.

    Writes ``sensitivity.json``, ``figures/pareto_frontier.png``,
    ``figures/sensitivity_benefit.png``, and a ``manifest.json`` mirroring the
    benchmark harness.
    """
    config_path = Path(config_path).resolve()
    config = load_config(config_path)
    run_id = run_id or config["run"]["id"]
    output_dir = Path(output_root) / run_id
    output_dir.mkdir(parents=True)
    (output_dir / "figures").mkdir()

    kernel, _ = load_or_build_kernel(config, config["run"]["kernel_cache_dir"])
    frontier = pareto_frontier(config, kernel, n_points=n_points)
    sweep = sensitivity_sweep(config)

    _json(output_dir / "sensitivity.json", {
        "config": str(config_path),
        "config_sha256": _sha256(config),
        "run_id": run_id,
        "pareto_frontier": frontier,
        "sensitivity_sweep": sweep,
    })

    pareto_frontier_figure(output_dir)
    sensitivity_benefit_figure(output_dir)

    import subprocess
    git_revision = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip() or "unknown"
    _json(output_dir / "manifest.json", {
        "run_id": run_id,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": git_revision,
        "config": str(config_path),
        "config_sha256": _sha256(config),
    })
    return output_dir
