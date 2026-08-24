from __future__ import annotations

import numpy as np
import xarray as xr


def generate_domain(config: dict) -> xr.Dataset:
    cfg = config["domain"]
    ny, nx = cfg["ny"], cfg["nx"]
    wet = np.ones((ny, nx), dtype=bool)
    wet[:, : cfg["coast_columns"]] = False
    # A deterministic, gently curved synthetic coastline.
    for row in range(ny):
        wet[row, : cfg["coast_columns"] + int(1.5 * np.sin(row / 7.0))] = False
    depth = np.where(wet, cfg["depth_m"] + np.arange(nx)[None, :] * 0.03, np.nan)
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
