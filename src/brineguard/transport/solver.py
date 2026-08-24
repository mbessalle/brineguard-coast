from __future__ import annotations

import numpy as np


def advance(concentration: np.ndarray, wet: np.ndarray, *, dx: float, dy: float, depth: float,
            u: float, v: float, dispersion: float, dt: float) -> np.ndarray:
    """One conservative finite-volume step with no-flux land/domain boundaries."""
    c = np.where(wet, concentration, 0.0)
    fx = np.zeros((c.shape[0], c.shape[1] + 1))
    fy = np.zeros((c.shape[0] + 1, c.shape[1]))
    pair_x = wet[:, :-1] & wet[:, 1:]
    pair_y = wet[:-1, :] & wet[1:, :]
    adv_x = u * np.where(u >= 0, c[:, :-1], c[:, 1:])
    adv_y = v * np.where(v >= 0, c[:-1, :], c[1:, :])
    fx[:, 1:-1] = np.where(pair_x, adv_x - dispersion * (c[:, 1:] - c[:, :-1]) / dx, 0.0)
    fy[1:-1, :] = np.where(pair_y, adv_y - dispersion * (c[1:, :] - c[:-1, :]) / dy, 0.0)
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
    for hour in range(hours):
        for _ in range(steps):
            for source in range(n_sources):
                c[sources[source]] += loads_kg_s[hour, source] * dcfg["transport_dt_s"] / cell_volume
            c = advance(c, wet, dx=dcfg["dx_m"], dy=dcfg["dy_m"], depth=dcfg["depth_m"],
                        u=dcfg["velocity_m_s"][0], v=dcfg["velocity_m_s"][1],
                        dispersion=dcfg["dispersion_m2_s"], dt=dcfg["transport_dt_s"])
        rec[hour] = [c[cell] for cell in receptors]
        if fields is not None:
            fields[hour] = c
    return rec, fields
