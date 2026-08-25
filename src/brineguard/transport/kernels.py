from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from brineguard.domain import generate_domain, receptor_cells, source_cells

# Bump when the kernel algorithm changes so stale cache entries can never be reused.
KERNEL_VERSION = "gaussian-puff-image-v1"


def _coast_face_x(wet_row: np.ndarray, dx: float) -> float:
    first_wet = int(np.argmax(wet_row))
    return (first_wet - 0.5) * dx


def build_kernel(config: dict) -> np.ndarray:
    """Return H[receptor, source, arrival_hour, release_hour] per kg/s.

    Semi-analytical source-receptor kernel (BUILD_PLAN 5.2): each hour of unit
    release is a train of Gaussian puffs matching the cross-check solver's
    injection cadence (one puff per transport substep), propagated exactly in
    continuous space with the physical dispersion — no grid, so no numerical
    diffusion. A single image source mirrored across the local coast face
    approximates the no-flux shoreline; open boundaries are treated as
    unbounded, which is valid while plumes stay far from the domain edge.

    Entries are computed per (release, arrival) pair from the actual elapsed
    times, not by shifting a single impulse response, so time-varying forcing
    only requires `_displacement` to integrate the forecast current — the
    kernel construction itself already supports nonstationarity.

    Depth-uniformity assumption is shared with the solver: the 1/h factor uses
    the scalar `depth_m`, not the spatially varying bathymetry field.
    """
    dcfg = config["domain"]
    hours = config["dispatch"]["horizon_hours"]
    dx, dy, depth = dcfg["dx_m"], dcfg["dy_m"], dcfg["depth_m"]
    dispersion = dcfg["dispersion_m2_s"]
    dt = dcfg["transport_dt_s"]
    steps = round(3600 / dt)
    u, v = dcfg["velocity_m_s"]
    wet = generate_domain(config)["wet"].values
    sources = source_cells(config)
    receptors = receptor_cells(config)

    def _displacement(ages_s: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return u * ages_s, v * ages_s

    kernel = np.zeros((len(receptors), len(sources), hours, hours))
    puff_mass = 1.0 * dt
    for s, (srow, scol) in enumerate(sources):
        xs, ys = scol * dx, srow * dy
        x_img = 2.0 * _coast_face_x(wet[srow], dx) - xs
        for release in range(hours):
            for arrival in range(release, hours):
                lag = arrival - release
                ages = (lag * steps + np.arange(1, steps + 1)) * dt
                shift_x, shift_y = _displacement(ages)
                denom = 4.0 * dispersion * ages
                for r, (rrow, rcol) in enumerate(receptors):
                    xr, yr = rcol * dx, rrow * dy
                    r2 = (xr - xs - shift_x) ** 2 + (yr - ys - shift_y) ** 2
                    r2_img = (xr - x_img - shift_x) ** 2 + (yr - ys - shift_y) ** 2
                    peaks = puff_mass / (np.pi * denom * depth)
                    kernel[r, s, arrival, release] = float(
                        np.sum(peaks * (np.exp(-r2 / denom) + np.exp(-r2_img / denom)))
                    )
    return kernel


def kernel_cache_key(config: dict) -> str:
    """Content address over exactly the inputs `build_kernel` reads.

    Dispatch economics (tariffs, weights, receptor thresholds/areas) are
    deliberately excluded so changing them reuses the cached kernel.
    """
    dcfg = config["domain"]
    payload = {
        "version": KERNEL_VERSION,
        "grid": [dcfg["ny"], dcfg["nx"], dcfg["dx_m"], dcfg["dy_m"]],
        "coast": [dcfg["coast_width_m"], dcfg["coast_amplitude_m"], dcfg["coast_wavelength_m"]],
        "depth_m": dcfg["depth_m"],
        "velocity_m_s": list(dcfg["velocity_m_s"]),
        "dispersion_m2_s": dcfg["dispersion_m2_s"],
        "transport_dt_s": dcfg["transport_dt_s"],
        "sources": source_cells(config),
        "receptors": receptor_cells(config),
        "horizon_hours": config["dispatch"]["horizon_hours"],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def load_or_build_kernel(config: dict, cache_dir: str | Path) -> tuple[np.ndarray, dict]:
    key = kernel_cache_key(config)
    cache_dir = Path(cache_dir)
    path = cache_dir / f"{key}.npz"
    if path.exists():
        with np.load(path) as archive:
            if str(archive["cache_key"]) == key:
                return archive["kernel"], {"cache_key": key, "cache_hit": True, "path": str(path)}
    kernel = build_kernel(config)
    cache_dir.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{key}.tmp-{os.getpid()}.npz")
    np.savez_compressed(temporary, kernel=kernel, cache_key=np.array(key))
    os.replace(temporary, path)
    return kernel, {"cache_key": key, "cache_hit": False, "path": str(path)}


def reconstruct(kernel: np.ndarray, loads_kg_s: np.ndarray) -> np.ndarray:
    return np.einsum("rits,si->tr", kernel, loads_kg_s)
