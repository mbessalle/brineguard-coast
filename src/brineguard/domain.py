from __future__ import annotations

import numpy as np
import xarray as xr


def generate_domain(config: dict) -> xr.Dataset:
    cfg = config["domain"]
    ny, nx = cfg["ny"], cfg["nx"]
    dx, dy = cfg["dx_m"], cfg["dy_m"]
    wet = np.ones((ny, nx), dtype=bool)
    # A deterministic, gently curved synthetic coastline, parameterized in metres so
    # grid refinement (smaller dx/dy) resolves the same physical shoreline.
    base_cells = int(cfg["coast_width_m"] / dx)
    wet[:, :base_cells] = False
    for row in range(ny):
        offset_cells = int(cfg["coast_amplitude_m"] * np.sin(row * dy / cfg["coast_wavelength_m"]) / dx)
        wet[row, : base_cells + offset_cells] = False
    depth = np.where(wet, cfg["depth_m"] + np.arange(nx)[None, :] * dx * cfg["depth_slope_per_m"], np.nan)
    ds = xr.Dataset(
        data_vars={"wet": (("y", "x"), wet), "depth_m": (("y", "x"), depth)},
        coords={"y": np.arange(ny) * cfg["dy_m"], "x": np.arange(nx) * cfg["dx_m"]},
        attrs={"crs": "LOCAL_CARTESIAN_METRES", "seed": config["run"]["seed"], "provenance": "deterministic synthetic fixture"},
    )
    return ds


def source_cells(config: dict) -> list[tuple[int, int]]:
    return [(item["row"], item["col"]) for item in config["domain"]["outfalls"]]


def receptor_cells(config: dict) -> list[tuple[int, int]]:
    return [(item["row"], item["col"]) for item in config["domain"]["receptors"]]
