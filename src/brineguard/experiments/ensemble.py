from __future__ import annotations

import copy

import numpy as np

from brineguard.dispatch.model import constant_schedule, solve_dispatch
from brineguard.dispatch.independent import solve_independent
from brineguard.transport.kernels import build_kernel
from brineguard.transport.solver import simulate

DEFAULT_PERTURB = {
    "u_mean_sigma_m_s": 0.005,
    "u_amp_sigma_m_s": 0.005,
    "phase_sigma_h": 1.0,
    "dispersion_sigma_rel": 0.15,
}


def _is_tidal(config: dict) -> bool:
    cur = config["domain"].get("currents")
    return cur is not None and cur["type"] == "tidal"


def _peak_u(config: dict) -> float:
    """Peak |u| (x-component) over a full cycle, mirroring the solver's
    `_peak_velocity` stability pre-check."""
    if _is_tidal(config):
        cur = config["domain"]["currents"]
        return abs(cur["u_mean_m_s"]) + abs(cur["u_amp_m_s"])
    return abs(config["domain"]["velocity_m_s"][0])


def _stability_cap(config: dict) -> float:
    """0.9 * (2*dispersion/dx): the conservative cap below the FD stability limit."""
    dcfg = config["domain"]
    return 0.9 * (2.0 * dcfg["dispersion_m2_s"] / dcfg["dx_m"])


def make_members(config: dict, n_members: int, seed: int,
                 perturb: dict | None = None) -> list[dict]:
    """Build an ensemble of deep-copied member configs (BUILD_PLAN §4.1, §5.3).

    Member 0 is always the unperturbed nominal. Members 1..n_members-1 are
    drawn from Gaussian perturbations via `numpy.random.default_rng(seed)`:
    dispersion is multiplicative lognormal (exp(N(0, sigma_rel))), currents are
    additive. Steady configs perturb `velocity_m_s`; tidal configs perturb
    `u_mean/u_amp/phase`. Any member whose peak |u| would exceed the stability
    cap is clipped to it and flagged `clipped` in its metadata.

    Returns a list of {"config": ..., "metadata": {...}} dicts.
    """
    perturb = {**DEFAULT_PERTURB, **(perturb or {})}
    rng = np.random.default_rng(seed)
    members = []
    for i in range(n_members):
        member_config = copy.deepcopy(config)
        dcfg = member_config["domain"]
        metadata: dict = {"index": i, "clipped": False}
        if i == 0:
            members.append({"config": member_config, "metadata": metadata})
            continue
        # Multiplicative dispersion perturbation (always, keeps it positive).
        disp_factor = float(np.exp(rng.normal(0.0, perturb["dispersion_sigma_rel"])))
        dcfg["dispersion_m2_s"] = dcfg["dispersion_m2_s"] * disp_factor
        metadata["dispersion_factor"] = disp_factor
        if _is_tidal(member_config):
            cur = dcfg["currents"]
            cur["u_mean_m_s"] += float(rng.normal(0.0, perturb["u_mean_sigma_m_s"]))
            cur["v_mean_m_s"] += float(rng.normal(0.0, perturb["u_mean_sigma_m_s"]))
            cur["u_amp_m_s"] += float(rng.normal(0.0, perturb["u_amp_sigma_m_s"]))
            cur["v_amp_m_s"] += float(rng.normal(0.0, perturb["u_amp_sigma_m_s"]))
            cur["phase_h"] += float(rng.normal(0.0, perturb["phase_sigma_h"]))
            metadata["currents"] = {k: cur[k] for k in
                                    ("u_mean_m_s", "v_mean_m_s", "u_amp_m_s", "v_amp_m_s", "phase_h")}
        else:
            u = dcfg["velocity_m_s"][0] + float(rng.normal(0.0, perturb["u_mean_sigma_m_s"]))
            v = dcfg["velocity_m_s"][1] + float(rng.normal(0.0, perturb["u_mean_sigma_m_s"]))
            dcfg["velocity_m_s"] = [u, v]
            metadata["velocity_m_s"] = [u, v]
        # Clip to the stability cap if the perturbation pushed peak |u| over it.
        cap = _stability_cap(member_config)
        peak = _peak_u(member_config)
        if peak > cap:
            if _is_tidal(member_config):
                cur = dcfg["currents"]
                scale = cap / peak if peak > 0 else 1.0
                cur["u_mean_m_s"] *= scale
                cur["u_amp_m_s"] *= scale
                cur["v_mean_m_s"] *= scale
                cur["v_amp_m_s"] *= scale
                metadata["currents"] = {k: cur[k] for k in
                                        ("u_mean_m_s", "v_mean_m_s", "u_amp_m_s", "v_amp_m_s", "phase_h")}
            else:
                u, v = dcfg["velocity_m_s"]
                scale = cap / peak if peak > 0 else 1.0
                dcfg["velocity_m_s"] = [u * scale, v * scale]
                metadata["velocity_m_s"] = list(dcfg["velocity_m_s"])
            metadata["clipped"] = True
            metadata["clipped_peak_u"] = float(_peak_u(member_config))
            metadata["cap"] = cap
        members.append({"config": member_config, "metadata": metadata})
    return members


def _exposure_sum(config: dict, rec: np.ndarray) -> float:
    """Area-weighted exceedance exposure_sum (BUILD_PLAN §7 primary metric)."""
    receptors = config["domain"]["receptors"]
    thresholds = np.array([r["threshold_kg_m3"] for r in receptors])
    areas = np.array([r["area_m2"] for r in receptors])
    exceedance = np.maximum(rec - thresholds[None, :], 0.0)
    return float(np.sum(areas[None, :] * exceedance))


def _held_out_stats(values: np.ndarray) -> dict:
    """Held-out summary over ensemble members EXCLUDING member 0."""
    held = np.asarray(values[1:], dtype=float)
    return {
        "mean": float(held.mean()),
        "std": float(held.std()),
        "p5": float(np.percentile(held, 5)),
        "p50": float(np.percentile(held, 50)),
        "p95": float(np.percentile(held, 95)),
    }


def _solve_nominal(strategy: str, config: dict, kernel: np.ndarray) -> dict:
    """Optimize the given strategy ONCE on the nominal member; return its frozen
    schedule (production and derived loads)."""
    if strategy == "A":
        return constant_schedule(config)
    if strategy == "B_capacity":
        return solve_independent(config, kernel, "capacity")
    if strategy == "B_cost":
        return solve_independent(config, kernel, "cost")
    if strategy == "C":
        return solve_dispatch(config, kernel)
    raise ValueError(f"Unknown strategy: {strategy}")


def evaluate_common_schedules(config: dict, n_members: int, seed: int,
                              perturb: dict | None = None,
                              strategies: tuple = ("A", "B_capacity", "B_cost", "C")) -> dict:
    """Common-schedule (held-out) ensemble evaluation (BUILD_PLAN §6.4-6.5, §10).

    Each strategy is optimized ONCE on the nominal member (member 0), then its
    frozen schedule is simulated against EVERY member config through the direct
    transport solver (no kernel needed for evaluation). Per strategy: per-member
    exposure_sum and held-out stats (mean/std/p5/p50/p95) over members EXCLUDING
    member 0. For each B rule, a per-member benefit_distribution
    (exposure_B - exposure_C)/exposure_B compares the same frozen schedules —
    cost matching is at the nominal only, a common-schedule comparison.
    """
    members = make_members(config, n_members, seed, perturb)
    nominal = members[0]["config"]
    kernel = build_kernel(nominal)
    result: dict = {"members": members, "strategies": {}}
    for strategy in strategies:
        schedule = _solve_nominal(strategy, nominal, kernel)
        loads = schedule["loads_kg_s"]
        exposure_per_member = []
        for member in members:
            rec, _ = simulate(member["config"], loads)
            exposure_per_member.append(_exposure_sum(member["config"], rec))
        entry: dict = {
            "exposure_per_member": exposure_per_member,
            "held_out": _held_out_stats(np.array(exposure_per_member)),
            "production_m3_h": schedule["production_m3_h"],
            "loads_kg_s": loads,
        }
        result["strategies"][strategy] = entry

    # Per-member matched pairing for each B rule (same frozen schedules).
    for rule in ("B_capacity", "B_cost"):
        if rule not in result["strategies"] or "C" not in result["strategies"]:
            continue
        exp_b = np.asarray(result["strategies"][rule]["exposure_per_member"], dtype=float)
        exp_c = np.asarray(result["strategies"]["C"]["exposure_per_member"], dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            benefit = np.where(exp_b > 0, (exp_b - exp_c) / exp_b, 0.0)
        result["strategies"][rule]["benefit_distribution"] = [float(b) for b in benefit]
        result["strategies"][rule]["benefit_nominal"] = float(benefit[0])
        result["strategies"][rule]["benefit_held_out"] = _held_out_stats(benefit)
    return result
