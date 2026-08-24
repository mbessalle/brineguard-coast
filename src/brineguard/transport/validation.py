from __future__ import annotations

import numpy as np

from brineguard.domain import generate_domain, source_cells
from brineguard.transport.solver import advance


def validate_pulse(config: dict) -> dict:
    dcfg, vcfg = config["domain"], config["validation"]
    domain = generate_domain(config)
    wet = domain["wet"].values
    c = np.zeros(wet.shape)
    source = source_cells(config)[1]
    volume = dcfg["dx_m"] * dcfg["dy_m"] * dcfg["depth_m"]
    c[source] = vcfg["pulse_mass_kg"] / volume
    elapsed = vcfg["pulse_hours"] * 3600
    for _ in range(round(elapsed / dcfg["transport_dt_s"])):
        c = advance(c, wet, dx=dcfg["dx_m"], dy=dcfg["dy_m"], depth=dcfg["depth_m"],
                    u=dcfg["velocity_m_s"][0], v=dcfg["velocity_m_s"][1],
                    dispersion=dcfg["dispersion_m2_s"], dt=dcfg["transport_dt_s"])
    final_mass = float(c.sum() * volume)
    mass_error = abs(final_mass - vcfg["pulse_mass_kg"]) / vcfg["pulse_mass_kg"]
    yy, xx = np.indices(c.shape)
    x0 = source[1] * dcfg["dx_m"] + dcfg["velocity_m_s"][0] * elapsed
    y0 = source[0] * dcfg["dy_m"] + dcfg["velocity_m_s"][1] * elapsed
    r2 = (xx * dcfg["dx_m"] - x0) ** 2 + (yy * dcfg["dy_m"] - y0) ** 2
    analytic = vcfg["pulse_mass_kg"] / (4 * np.pi * dcfg["dispersion_m2_s"] * elapsed * dcfg["depth_m"]) * np.exp(
        -r2 / (4 * dcfg["dispersion_m2_s"] * elapsed)
    )
    analytic[~wet] = 0.0
    # Normalize the sampled analytical field: comparison is shape-based while mass has its own audit.
    analytic *= vcfg["pulse_mass_kg"] / (analytic.sum() * volume)
    rel_l1 = float(np.abs(c - analytic).sum() / analytic.sum())
    result = {
        "initial_mass_kg": vcfg["pulse_mass_kg"], "final_mass_kg": final_mass,
        "mass_relative_error": mass_error, "mass_pass": mass_error <= vcfg["mass_relative_tolerance"],
        "analytical_relative_l1_error": rel_l1,
        "analytical_pass": rel_l1 <= vcfg["analytical_relative_l1_tolerance"],
    }
    return result
