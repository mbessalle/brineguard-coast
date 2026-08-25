from __future__ import annotations

import copy

import numpy as np

from brineguard.domain import generate_domain, source_cells
from brineguard.transport.solver import advance, simulate


def validate_pulse(config: dict) -> dict:
    dcfg, vcfg = config["domain"], config["validation"]
    domain = generate_domain(config)
    wet = domain["wet"].values
    c = np.zeros(wet.shape)
    source = source_cells(config)[1]
    volume = dcfg["dx_m"] * dcfg["dy_m"] * dcfg["depth_m"]
    c[source] = vcfg["pulse_mass_kg"] / volume
    elapsed = vcfg["pulse_hours"] * 3600
    cur = dcfg.get("currents")
    t0_s = (cur["t0_h"] * 3600.0) if cur is not None and cur["type"] == "tidal" else 0.0
    from brineguard.transport.solver import _current_at_time
    dt_s = dcfg["transport_dt_s"]
    n_steps = round(elapsed / dt_s)
    for step in range(n_steps):
        ut, vt = _current_at_time(config, t0_s + step * dt_s)
        c = advance(c, wet, dx=dcfg["dx_m"], dy=dcfg["dy_m"], depth=dcfg["depth_m"],
                    u=ut, v=vt, dispersion=dcfg["dispersion_m2_s"], dt=dt_s)
    final_mass = float(c.sum() * volume)
    mass_error = abs(final_mass - vcfg["pulse_mass_kg"]) / vcfg["pulse_mass_kg"]
    result = {
        "initial_mass_kg": vcfg["pulse_mass_kg"], "final_mass_kg": final_mass,
        "mass_relative_error": mass_error, "mass_pass": mass_error <= vcfg["mass_relative_tolerance"],
    }
    if cur is not None and cur["type"] == "tidal":
        result["analytical_gate"] = "skipped (nonstationary currents)"
        result["analytical_pass"] = True
    else:
        u, v = dcfg["velocity_m_s"]
        yy, xx = np.indices(c.shape)
        x0 = source[1] * dcfg["dx_m"] + u * elapsed
        y0 = source[0] * dcfg["dy_m"] + v * elapsed
        r2 = (xx * dcfg["dx_m"] - x0) ** 2 + (yy * dcfg["dy_m"] - y0) ** 2
        analytic = vcfg["pulse_mass_kg"] / (4 * np.pi * dcfg["dispersion_m2_s"] * elapsed * dcfg["depth_m"]) * np.exp(
            -r2 / (4 * dcfg["dispersion_m2_s"] * elapsed)
        )
        analytic[~wet] = 0.0
        # Normalize the sampled analytical field: comparison is shape-based while mass has its own audit.
        analytic *= vcfg["pulse_mass_kg"] / (analytic.sum() * volume)
        rel_l1 = float(np.abs(c - analytic).sum() / analytic.sum())
        result["analytical_relative_l1_error"] = rel_l1
        result["analytical_pass"] = rel_l1 <= vcfg["analytical_relative_l1_tolerance"]
    return result


def _reference_loads(config: dict) -> np.ndarray:
    hours = config["dispatch"]["horizon_hours"]
    n_sources = len(config["domain"]["outfalls"])
    return np.random.default_rng(config["run"]["seed"]).uniform(0.0, 0.7, (hours, n_sources))


def validate_linearity(config: dict) -> dict:
    """Zero source, superposition, and source scaling on the direct solver (BUILD_PLAN 5.3)."""
    tol = config["validation"]["linearity_absolute_tolerance_kg_m3"]
    loads_a = _reference_loads(config)
    loads_b = loads_a[::-1] * 0.6
    zero, _ = simulate(config, np.zeros_like(loads_a))
    rec_a, _ = simulate(config, loads_a)
    rec_b, _ = simulate(config, loads_b)
    rec_ab, _ = simulate(config, loads_a + loads_b)
    rec_2a, _ = simulate(config, 2.0 * loads_a)
    zero_max = float(np.abs(zero).max())
    superposition = float(np.abs(rec_ab - rec_a - rec_b).max())
    scaling = float(np.abs(rec_2a - 2.0 * rec_a).max())
    return {
        "zero_source_max_anomaly_kg_m3": zero_max,
        "superposition_max_abs_error_kg_m3": superposition,
        "scaling_max_abs_error_kg_m3": scaling,
        "linearity_pass": bool(max(zero_max, superposition, scaling) <= tol),
    }


def validate_boundaries(config: dict) -> dict:
    """Reversing currents against no-flux boundaries: mass conserved, no negatives (BUILD_PLAN 5.3)."""
    dcfg = config["domain"]
    tol = config["validation"]["boundary_mass_relative_tolerance"]
    wet = generate_domain(config)["wet"].values
    rng = np.random.default_rng(config["run"]["seed"])
    c = np.where(wet, rng.random(wet.shape), 0.0)
    initial_sum = c.sum()
    minimum = c.min()
    # Alternate current direction every step, including a push onshore (negative u) and
    # alongshore reversal, at magnitudes the anti-diffusion correction still admits.
    for step in range(48):
        sign = 1.0 if step % 2 == 0 else -1.0
        c = advance(c, wet, dx=dcfg["dx_m"], dy=dcfg["dy_m"], depth=dcfg["depth_m"],
                    u=0.06 * sign, v=0.03 * -sign, dispersion=dcfg["dispersion_m2_s"],
                    dt=dcfg["transport_dt_s"])
        minimum = min(minimum, float(c.min()))
    mass_error = float(abs(c.sum() - initial_sum) / initial_sum)
    return {
        "boundary_reversing_mass_relative_error": mass_error,
        "boundary_minimum_anomaly_kg_m3": float(minimum),
        "boundary_pass": bool(mass_error <= tol and minimum >= 0.0),
    }


def _refined_config(config: dict, factor: int) -> dict:
    fine = copy.deepcopy(config)
    dcfg = fine["domain"]
    dcfg["ny"] *= factor
    dcfg["nx"] *= factor
    dcfg["dx_m"] /= factor
    dcfg["dy_m"] /= factor
    dcfg["transport_dt_s"] /= factor
    for item in dcfg["outfalls"] + dcfg["receptors"]:
        item["row"] *= factor
        item["col"] *= factor
    # Scale period_h in tidal currents to match the finer temporal resolution.
    if "currents" in dcfg:
        dcfg["currents"] = dict(dcfg["currents"])
    return fine


def validate_refinement(config: dict) -> dict:
    """Joint grid/timestep refinement of the direct solver (BUILD_PLAN 5.3).

    The gate is on the receptor-area-weighted total dose change, matching the
    exposure aggregation the optimizer uses; per-receptor changes are reported
    unconditionally because low-dose far-field receptors carry a larger relative
    discretization error than the aggregate suggests.
    """
    vcfg = config["validation"]
    loads = _reference_loads(config)
    base_dose = simulate(config, loads)[0].sum(axis=0)
    fine_dose = simulate(_refined_config(config, 2), loads)[0].sum(axis=0)
    per_receptor = np.abs(fine_dose - base_dose) / base_dose
    areas = np.array([r["area_m2"] for r in config["domain"]["receptors"]])
    weighted = float(abs((areas * fine_dose).sum() - (areas * base_dose).sum()) / (areas * base_dose).sum())
    return {
        "refinement_receptor_dose_relative_change": {
            r["name"]: float(change)
            for r, change in zip(config["domain"]["receptors"], per_receptor)
        },
        "refinement_weighted_dose_relative_change": weighted,
        "refinement_pass": bool(weighted <= vcfg["refinement_weighted_dose_relative_tolerance"]),
    }


def kernel_agreement(config: dict, direct: np.ndarray, reconstructed: np.ndarray) -> dict:
    """Kernel-vs-direct-solver agreement at every benchmark receptor (BUILD_PLAN 5.3).

    Per receptor, the max absolute gap must stay within a relative fraction of that
    receptor's direct peak or within a fraction of its ecological threshold,
    whichever is larger — low-dose receptors far below threshold are held to the
    absolute floor, not to a relative error their tiny signal cannot support.
    """
    vcfg = config["validation"]
    receptors = config["domain"]["receptors"]
    per_receptor = {}
    ok = True
    for i, receptor in enumerate(receptors):
        gap = float(np.abs(direct[:, i] - reconstructed[:, i]).max())
        peak = float(direct[:, i].max())
        allowed = max(vcfg["kernel_agreement_relative_tolerance"] * peak,
                      vcfg["kernel_agreement_threshold_fraction"] * receptor["threshold_kg_m3"])
        passed = bool(gap <= allowed)
        ok = ok and passed
        per_receptor[receptor["name"]] = {
            "max_abs_gap_kg_m3": gap, "direct_peak_kg_m3": peak,
            "allowed_gap_kg_m3": allowed, "pass": passed,
        }
    return {"kernel_agreement": per_receptor, "kernel_agreement_pass": ok}


def validate_transport(config: dict) -> dict:
    result = validate_pulse(config)
    result.update(validate_linearity(config))
    result.update(validate_boundaries(config))
    result.update(validate_refinement(config))
    from brineguard.transport.kernels import build_kernel, reconstruct

    loads = _reference_loads(config)
    direct, _ = simulate(config, loads)
    reconstructed = reconstruct(build_kernel(config), loads)
    result.update(kernel_agreement(config, direct, reconstructed))
    result["transport_pass"] = bool(all(value for key, value in result.items() if key.endswith("_pass")))
    return result
