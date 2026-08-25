from __future__ import annotations

import numpy as np


def _current_at_time(config: dict, t_s: float) -> tuple[float, float]:
    """Evaluate (u, v) at absolute time t_s (seconds) for tidal or steady currents."""
    cur = config["domain"].get("currents")
    if cur is not None and cur["type"] == "tidal":
        period_s = cur["period_h"] * 3600.0
        phase_s = cur["phase_h"] * 3600.0
        omega = 2.0 * np.pi / period_s
        arg = omega * (t_s - phase_s)
        cos_val = np.cos(arg)
        return (cur["u_mean_m_s"] + cur["u_amp_m_s"] * cos_val,
                cur["v_mean_m_s"] + cur["v_amp_m_s"] * cos_val)
    u, v = config["domain"]["velocity_m_s"]
    return u, v


def _peak_velocity(config: dict, horizon_hours: int) -> tuple[float, float]:
    """Peak |u|,|v| over the simulated window for stability pre-check."""
    cur = config["domain"].get("currents")
    if cur is not None and cur["type"] == "tidal":
        return (abs(cur["u_mean_m_s"]) + abs(cur["u_amp_m_s"]),
                abs(cur["v_mean_m_s"]) + abs(cur["v_amp_m_s"]))
    u, v = config["domain"]["velocity_m_s"]
    return abs(u), abs(v)


def advance(concentration: np.ndarray, wet: np.ndarray, *, dx: float, dy: float, depth: float,
            u: float, v: float, dispersion: float, dt: float) -> np.ndarray:
    """One conservative finite-volume step with no-flux land/domain boundaries.

    The diffusive flux uses an anti-diffusion (modified-equation) correction:
    first-order upwind advection adds numerical diffusion |u|*dx/2*(1-CFL) per
    direction, so that amount is subtracted from the physical dispersion to keep
    the effective dispersion at the physical value to O(dx^2). The correction is
    only valid while it leaves a nonnegative coefficient — advection-dominated
    configurations (fast currents on a coarse grid) raise instead of silently
    running over-diffusive.

    `depth` is accepted but unused: this solves the depth-averaged equation
    d(hc)/dt + div(huc) = div(hD grad c) only in the special case where h is
    spatially and temporally uniform, so it cancels from every term. The h field
    `domain.generate_domain` produces (which varies with column, per BUILD_PLAN
    4.1's "variable depth") is therefore not actually applied to transport
    anywhere in this solver — `simulate`/`validate_pulse` both use the single
    scalar `dcfg["depth_m"]` for cell volume instead. Passing a spatially-varying
    depth array here would silently give wrong results, not an error.
    """
    dispersion_x = dispersion - 0.5 * abs(u) * dx * (1.0 - abs(u) * dt / dx)
    dispersion_y = dispersion - 0.5 * abs(v) * dy * (1.0 - abs(v) * dt / dy)
    if dispersion_x < 0 or dispersion_y < 0:
        raise ValueError(
            "Anti-diffusion correction would produce a negative dispersion coefficient: "
            "the grid is too coarse for this current speed; refine dx/dy or reduce velocity"
        )
    c = np.where(wet, concentration, 0.0)
    fx = np.zeros((c.shape[0], c.shape[1] + 1))
    fy = np.zeros((c.shape[0] + 1, c.shape[1]))
    pair_x = wet[:, :-1] & wet[:, 1:]
    pair_y = wet[:-1, :] & wet[1:, :]
    adv_x = u * np.where(u >= 0, c[:, :-1], c[:, 1:])
    adv_y = v * np.where(v >= 0, c[:-1, :], c[1:, :])
    fx[:, 1:-1] = np.where(pair_x, adv_x - dispersion_x * (c[:, 1:] - c[:, :-1]) / dx, 0.0)
    fy[1:-1, :] = np.where(pair_y, adv_y - dispersion_y * (c[1:, :] - c[:-1, :]) / dy, 0.0)
    updated = c - dt * ((fx[:, 1:] - fx[:, :-1]) / dx + (fy[1:, :] - fy[:-1, :]) / dy)
    updated[~wet] = 0.0
    if updated.min() < -1e-12:
        raise RuntimeError("Transport stability failure produced negative concentration")
    return np.maximum(updated, 0.0)


def simulate(config: dict, loads_kg_s: np.ndarray, *, initial: np.ndarray | None = None,
             record_full: bool = False) -> tuple[np.ndarray, np.ndarray | None]:
    """Simulate hourly piecewise-constant loads; return receptor and optional full-grid states."""
    from brineguard.domain import generate_domain, receptor_cells, source_cells

    dcfg = config["domain"]
    wet = generate_domain(config)["wet"].values
    c = np.zeros(wet.shape) if initial is None else initial.copy()
    hours, n_sources = loads_kg_s.shape
    steps = round(3600 / dcfg["transport_dt_s"])
    cell_volume = dcfg["dx_m"] * dcfg["dy_m"] * dcfg["depth_m"]
    receptors = receptor_cells(config)
    sources = source_cells(config)
    rec = np.zeros((hours, len(receptors)))
    fields = np.zeros((hours, *wet.shape)) if record_full else None
    cur = dcfg.get("currents")
    t0_s = (cur["t0_h"] * 3600.0) if cur is not None and cur["type"] == "tidal" else 0.0
    peak_u, peak_v = _peak_velocity(config, hours)
    peak_dx = dcfg["dispersion_m2_s"] - 0.5 * peak_u * dcfg["dx_m"]
    if peak_dx < 0:
        raise ValueError(
            "Anti-diffusion correction would produce a negative dispersion coefficient "
            "for the peak velocity over the simulated window: "
            f"|u|={peak_u:.3f} m/s exceeds the stability cap on the {dcfg['dx_m']:.0f} m grid"
        )
    dt_s = dcfg["transport_dt_s"]
    elapsed = 0.0
    for hour in range(hours):
        for _ in range(steps):
            for source in range(n_sources):
                c[sources[source]] += loads_kg_s[hour, source] * dt_s / cell_volume
            ut, vt = _current_at_time(config, t0_s + elapsed)
            c = advance(c, wet, dx=dcfg["dx_m"], dy=dcfg["dy_m"], depth=dcfg["depth_m"],
                        u=ut, v=vt, dispersion=dcfg["dispersion_m2_s"], dt=dt_s)
            elapsed += dt_s
        rec[hour] = [c[cell] for cell in receptors]
        if fields is not None:
            fields[hour] = c
    return rec, fields
