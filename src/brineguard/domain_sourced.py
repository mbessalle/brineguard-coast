"""Hybrid sourced domain from real GEBCO bathymetry with explicit checks.

BUILD_PLAN Phase 4: when the sourced-domain resolution/provenance/geometry
checks fail, fall back to an explicitly hybrid domain — real bathymetry,
assumed plants — and never imply site accuracy.

The domain contract exactly mirrors `brineguard.domain.generate_domain`:
wet (bool), depth_m (float, uniform scalar — see below), y/x coords in
metres, and attrs with provenance, crs, and the BUILD_PLAN-mandated label.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import xarray as xr

from brineguard.domain import generate_domain  # noqa: F401 — used by get_domain dispatch

# Metres per degree of latitude (WGS-84 mean meridional arc — the standard
# 1 arc-minute ≈ 1855.33 m approximation gives 111 320 m/deg, which is the
# same constant used by many coastal oceanography screening tools).
METRES_PER_DEG_LAT: float = 111320.0

# GEBCO 2025 / 2021 native grid resolution in arc-seconds.
GEBCO_ARC_SECONDS: float = 15.0

# Attrs label mandated by BUILD_PLAN Phase 4 — must be written into every
# hybrid dataset so reviewers can never mistake it for a site-specific claim.
HYBRID_LABEL: str = (
    "HYBRID DOMAIN - real GEBCO bathymetry, ASSUMED plants; "
    "not a site-specific claim"
)


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------


def _elevation_variable(ds: xr.Dataset) -> xr.DataArray:
    """Locate the elevation data variable in a GEBCO netCDF (multiple naming conventions)."""
    for name in ("elevation", "Elevation", "z", "Z", "bathymetry", "Band1"):
        if name in ds.variables:
            return ds[name]
    raise ValueError(f"No recognised elevation variable in {list(ds.variables)}")


def _registry_json_path(path: str | Path) -> Path:
    return Path(path).with_suffix(".json")


def _read_registry_sha(gebco_path: str | Path) -> str | None:
    """sha256 from the provenance JSON shipped alongside the netCDF, or None."""
    prov_path = _registry_json_path(gebco_path)
    if not prov_path.exists():
        return None
    try:
        return json.loads(prov_path.read_text(encoding="utf-8"))["sha256"]
    except (KeyError, json.JSONDecodeError):
        return None


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_and_project(config: dict) -> tuple[np.ndarray, np.ndarray, int, int, float]:
    """Return (wet, elevation, ny, nx, mean_lat) for the source bbox.

    Projection uses simple equirectangular scaling::
        y = (lat − lat_min) · METRES_PER_DEG_LAT
        x = (lon − lon_min) · METRES_PER_DEG_LAT · cos(mean_lat)

    This is a plane-sailing approximation that treats the GEBCO bounding box
    as locally flat.  It is accurate to O(Δlat²) and is adequate for a
    screening model at 20–30 km domain size — *not* suitable for
    centimetre-level coordinate work.
    """
    dcfg = config["domain"]
    lat_min, lat_max, lon_min, lon_max = (float(v) for v in dcfg["bbox"])
    dx = float(dcfg["dx_m"])
    dy = float(dcfg["dy_m"])

    mean_lat = (lat_min + lat_max) / 2.0
    mpd_lon = METRES_PER_DEG_LAT * np.cos(np.radians(mean_lat))

    ny = int(round((lat_max - lat_min) * METRES_PER_DEG_LAT / dy))
    nx = int(round((lon_max - lon_min) * mpd_lon / dx))

    gebco_path = Path(dcfg["gebco_path"])
    ds = xr.open_dataset(gebco_path, engine="scipy")
    elev_arr = _elevation_variable(ds).values
    lats = ds["latitude"].values
    lons = ds["longitude"].values
    ds.close()

    # Cell-centre lat/lon on the projected grid.
    lat_c = lat_min + (np.arange(ny, dtype=float) + 0.5) * dy / METRES_PER_DEG_LAT
    lon_c = lon_min + (np.arange(nx, dtype=float) + 0.5) * dx / mpd_lon

    # Nearest-GEBCO-cell sampling (native 463 m → 500 m grids are similar
    # enough that linear interpolation is overkill here).
    li = np.searchsorted(lats, lat_c).clip(0, len(lats) - 1)
    lj = np.searchsorted(lons, lon_c).clip(0, len(lons) - 1)

    elevation = elev_arr[np.ix_(li, lj)]
    wet = elevation < 0  # GEBCO elevation: positive = above MSL, negative = below
    return wet, elevation, ny, nx, mean_lat


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def checks(config: dict) -> dict:
    """Validate the hybrid domain configuration against BUILD_PLAN Phase 4 gates.

    Returns
    -------
    dict
        {provenance_pass, resolution_pass, geometry_pass, details}.
        ``details`` is a nested dict with human-readable per-gate
        explanations — suitable for audit and error messages.
    """
    dcfg = config["domain"]
    gebco_path = Path(dcfg["gebco_path"])
    dx = float(dcfg["dx_m"])

    # ---- provenance ----------------------------------------------------------
    prov_pass = False
    recorded_sha = _read_registry_sha(gebco_path)
    if recorded_sha is None:
        prov_detail = "registry JSON missing or unreadable"
    else:
        actual_sha = _sha256_file(gebco_path)
        if actual_sha == recorded_sha:
            prov_pass = True
            prov_detail = f"sha256 matches {recorded_sha[:16]}…"
        else:
            prov_detail = (
                f"sha256 mismatch: registry {recorded_sha[:16]}… "
                f"vs file {actual_sha[:16]}…"
            )

    # ---- resolution ----------------------------------------------------------
    lat_min, lat_max, lon_min, lon_max = (float(v) for v in dcfg["bbox"])
    mean_lat = (lat_min + lat_max) / 2.0
    native_lat_m = METRES_PER_DEG_LAT / (3600.0 / GEBCO_ARC_SECONDS)  # ≈ 463.8 m
    native_lon_m = native_lat_m * float(np.cos(np.radians(mean_lat)))
    native_m = max(native_lat_m, native_lon_m)
    res_pass = native_m <= 2.0 * dx
    res_detail = (
        f"GEBCO {GEBCO_ARC_SECONDS:.0f}″ native cell {native_m:.1f} m "
        f"≤ 2·dx = {2.0 * dx:.1f} m"
    )

    # ---- geometry ------------------------------------------------------------
    wet, _elev, ny, nx, _ = _load_and_project(config)
    grid_pass = ny >= 20 and nx >= 20

    # Contiguous coastline: at least one dry cell horizontally adjacent to a
    # wet cell in ≥ 80 % of rows.
    dry = ~wet
    adjacent = (dry[:, :-1] & wet[:, 1:]) | (dry[:, 1:] & wet[:, :-1])
    coast_rows = int(adjacent.any(axis=1).sum())
    coast_frac = float(coast_rows) / float(ny)
    coastline_pass = coast_frac >= 0.8

    outfalls = [(it["row"], it["col"]) for it in dcfg["outfalls"]]
    receptors = [(it["row"], it["col"]) for it in dcfg["receptors"]]
    all_wet = all(wet[r, c] for r, c in outfalls + receptors)

    geom_pass = bool(grid_pass and coastline_pass and all_wet)
    geom_detail = {
        "grid": f"{ny}×{nx}",
        "grid_pass": grid_pass,
        "coastline_rows_fraction": round(coast_frac, 4),
        "coastline_pass": coastline_pass,
        "outfalls_receptors_wet": all_wet,
    }

    return {
        "provenance_pass": prov_pass,
        "resolution_pass": res_pass,
        "geometry_pass": geom_pass,
        "details": {
            "provenance": prov_detail,
            "resolution": res_detail,
            "geometry": geom_detail,
        },
    }


def build_hybrid_domain(config: dict) -> xr.Dataset:
    """Build a hybrid sourced domain from GEBCO bathymetry + assumed plants.

    Contracts
    ---------
    * Same return type as ``brineguard.domain.generate_domain``.
    * Depth is a **uniform scalar**: ``median(|bathymetry|)`` clipped to
      [5 m, 30 m], with the true (unclipped) median recorded in
      ``attrs["depth_true_median_m"]``.  This is the kernel/solver
      uniform-depth simplification documented in BUILD_PLAN §5.2.
    * Raises ``ValueError`` if any Phase 4 gate fails, *unless*
      ``config["domain"]["allow_hybrid_fallback"]`` is true, in which case
      it proceeds and stamps ``attrs["checks_failed"]``.
    """
    dcfg = config["domain"]
    result = checks(config)
    failures = [k for k in ("provenance_pass", "resolution_pass", "geometry_pass") if not result[k]]
    allow_fallback = bool(dcfg.get("allow_hybrid_fallback", False))
    if failures and not allow_fallback:
        raise ValueError(
            f"Hybrid domain checks failed: {failures}. Details: {result['details']}"
        )

    wet, elevation, ny, nx, mean_lat = _load_and_project(config)
    dx = float(dcfg["dx_m"])
    dy = float(dcfg["dy_m"])

    # Uniform-depth simplification (BUILD_PLAN §5.2).
    depths = -elevation[wet]  # positive depth where water
    true_median = float(np.median(depths))
    uniform_depth = float(np.clip(true_median, 5.0, 30.0))

    depth_m = np.where(wet, uniform_depth, np.nan)

    prov_sha = _read_registry_sha(dcfg["gebco_path"])
    mpd_lon = METRES_PER_DEG_LAT * np.cos(np.radians(mean_lat))
    attrs = {
        "crs": "LOCAL_CARTESIAN_METRES",
        "provenance": "hybrid sourced domain: real GEBCO bathymetry, assumed plants",
        "source": "gebco",
        "gebco_path": str(dcfg["gebco_path"]),
        "bbox": [float(v) for v in dcfg["bbox"]],
        "gebco_sha256": prov_sha if prov_sha else "unavailable",
        "depth_true_median_m": true_median,
        "depth_uniform_m": uniform_depth,
        "projection": (
            f"equirectangular, cos(mean_lat={mean_lat:.4f}) longitudinal scaling; "
            f"mpd_lat={METRES_PER_DEG_LAT:.0f} mpd_lon={mpd_lon:.1f}"
        ),
        "label": HYBRID_LABEL,
    }
    if failures:
        attrs["checks_failed"] = failures

    ds = xr.Dataset(
        data_vars={
            "wet": (("y", "x"), wet),
            "depth_m": (("y", "x"), depth_m),
        },
        coords={
            "y": np.arange(ny, dtype=float) * dy,
            "x": np.arange(nx, dtype=float) * dx,
        },
        attrs=attrs,
    )
    return ds


def get_domain(config: dict) -> xr.Dataset:
    """Generate-compatible dispatch.

    Returns ``build_hybrid_domain(config)`` when ``config["domain"]["source"]``
    is ``"gebco"``, otherwise delegates to ``brineguard.domain.generate_domain``.
    """
    if config["domain"].get("source") == "gebco":
        return build_hybrid_domain(config)
    return generate_domain(config)