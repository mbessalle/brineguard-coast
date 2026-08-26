"""Extract sub-tidal mean circulation summary from CMEMS Red Sea daily-mean
currents for screening-level parameter extraction.

IMPORTANT: Daily-mean data cannot resolve the M2 tide (12.42 h).  The
measured quantity is the **sub-tidal mean circulation**; the tidal
component remains analytic-assumed in every output artifact and docstring.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import xarray as xr


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def extract_current_summary(nc_path: str | Path, depth_max_m: float = 30.0) -> dict:
    """Compute a deterministic sub-tidal mean circulation summary.

    The function is **pure computation** — no network, no I/O beyond
    reading *nc_path* and its sibling provenance JSON.

    Parameters
    ----------
    nc_path : str or Path
        Path to the CMEMS daily-mean netCDF (uo, vo).
    depth_max_m : float
        Maximum depth (m) for the depth-averaging window (inclusive).

    Returns
    -------
    dict
        Keys: ``u_mean_m_s``, ``v_mean_m_s``, ``mean_speed_m_s``,
        ``max_daily_speed_m_s``, ``speed_std_m_s``, ``n_days``,
        ``depth_levels_used``, ``provenance_sha256``, ``dataset_id``.
        ``coverage_warning`` is present (set to ``True``) when >50 % of
        spatial cells are NaN/land-masked.

    Notes
    -----
    * The tidal component (M2, 12.42 h) **cannot** be resolved from
      daily-mean data and remains analytic-assumed.
    * NaN/land cells are excluded via the dataset mask; the mask is
      computed as cells that are finite in all time steps after
      depth-averaging.
    """
    nc_path = Path(nc_path)
    ds = xr.open_dataset(str(nc_path), engine="h5netcdf")

    # Depth levels ≤ depth_max_m.
    depth_mask = ds.depth.values <= depth_max_m
    depth_levels = [float(v) for v in ds.depth.values[depth_mask]]

    # Slice to shallow depths.
    uo_shallow = ds["uo"].isel(depth=depth_mask)  # (time, depth, lat, lon)
    vo_shallow = ds["vo"].isel(depth=depth_mask)

    # Depth-average (mean over the shallow depth levels).
    uo_da = uo_shallow.mean(dim="depth")  # (time, lat, lon)
    vo_da = vo_shallow.mean(dim="depth")

    # Water mask: cells finite at every time step after depth-averaging.
    water_mask = (
        uo_da.notnull().all(dim="time").values
        & vo_da.notnull().all(dim="time").values
    )
    n_water = int(water_mask.sum())
    n_total = water_mask.size
    coverage = float(n_water) / float(n_total)

    # Spatial-mean time series (over water cells only).
    u_spatial = uo_da.where(water_mask).mean(dim=("latitude", "longitude"))  # (time,)
    v_spatial = vo_da.where(water_mask).mean(dim=("latitude", "longitude"))

    u_mean = float(u_spatial.mean(dim="time").values)
    v_mean = float(v_spatial.mean(dim="time").values)

    speed = np.sqrt(u_spatial.values ** 2 + v_spatial.values ** 2)
    mean_speed = float(np.mean(speed))
    max_daily_speed = float(np.max(speed))
    speed_std = float(np.std(speed))
    n_days = int(ds.sizes["time"])

    ds.close()

    # Provenance from the sibling JSON.
    prov_path = nc_path.with_suffix(".json")
    prov = json.loads(prov_path.read_text(encoding="utf-8"))

    result: dict = {
        "u_mean_m_s": u_mean,
        "v_mean_m_s": v_mean,
        "mean_speed_m_s": mean_speed,
        "max_daily_speed_m_s": max_daily_speed,
        "speed_std_m_s": speed_std,
        "n_days": n_days,
        "depth_levels_used": depth_levels,
        "provenance_sha256": prov["sha256"],
        "dataset_id": prov["dataset_id"],
    }
    if coverage < 0.5:
        result["coverage_warning"] = True
    return result