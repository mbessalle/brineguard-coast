#!/usr/bin/env python3
"""Download a GEBCO bathymetry subset for a bounding box as netCDF.

Uses a public ERDDAP server (no auth required) to subset the GEBCO grid.
On success: saves under data/registry/gebco/ with provenance JSON alongside.

Usage:
  python3 tools/fetch_gebco.py                          # default Red Sea corridor
  python3 tools/fetch_gebco.py --bbox 26 29 34 37 -o my_bathy.nc
  python3 tools/fetch_gebco.py --url-template "https://HOST/erddap/griddap/DATASET.nc?elevation[({lat_min}):1:({lat_max})][({lon_min}):1:({lon_max})]"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_URL_TEMPLATE = (
    "https://erddap.ifremer.fr/erddap/griddap/gebco2021.nc"
    "?elevation[({lat_min}):1:({lat_max})][({lon_min}):1:({lon_max})]"
)
DEFAULT_BBOX = (26, 29, 34, 37)  # lat_min, lat_max, lon_min, lon_max
REGISTRY_DIR = Path("data/registry/gebco")


def _validate_netcdf(path: str) -> bool:
    """Check file starts with a recognised netCDF magic number."""
    with open(path, "rb") as fh:
        head = fh.read(4)
    # netCDF-3: CDF\001, CDF\002; netCDF-4/HDF5: \x89HDF
    return head in (b"CDF\x01", b"CDF\x02", b"\x89HDF")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download GEBCO bathymetry subset via ERDDAP (public, no auth)."
    )
    parser.add_argument(
        "--url-template",
        default=DEFAULT_URL_TEMPLATE,
        help="ERDDAP griddap URL template. Placeholders: {lat_min}, {lat_max}, "
             "{lon_min}, {lon_max}. Default: IFREMER ERDDAP gebco2021.",
    )
    parser.add_argument(
        "--bbox", nargs=4, type=float, default=DEFAULT_BBOX,
        metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"),
        help="Bounding box (default: Red Sea corridor 26 29 34 37).",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output netCDF path (default: data/registry/gebco/gebco_<bbox>.nc).",
    )
    args = parser.parse_args()

    lat_min, lat_max, lon_min, lon_max = args.bbox
    if lat_min >= lat_max:
        parser.error("LAT_MIN must be < LAT_MAX")
    if lon_min >= lon_max:
        parser.error("LON_MIN must be < LON_MAX")

    # Build the raw URL with placeholders, then URL-encode brackets for ERDDAP
    raw_url = args.url_template.format(
        lat_min=lat_min, lat_max=lat_max, lon_min=lon_min, lon_max=lon_max,
    )
    # ERDDAP requires brackets in query strings; urllib won't encode them for
    # us in a way that works, so do it explicitly.
    url = raw_url.replace("[", "%5B").replace("]", "%5D")

    if args.output:
        out_path = Path(args.output)
    else:
        REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        tag = f"lat{lat_min}_{lat_max}_lon{lon_min}_{lon_max}".replace(".", "p")
        out_path = REGISTRY_DIR / f"gebco_{tag}.nc"

    print(f"Fetching: {url}", file=sys.stderr)
    try:
        urllib.request.urlretrieve(url, str(out_path))
    except urllib.error.HTTPError as e:
        body_head = ""
        try:
            body_head = e.read(1024).decode("utf-8", errors="replace")
        except Exception:
            pass
        print(
            f"HTTP {e.code} {e.reason}\n{body_head}",
            file=sys.stderr,
        )
        if out_path.exists():
            out_path.unlink()
        sys.exit(1)
    except Exception as e:
        print(f"Download failed: {e}", file=sys.stderr)
        if out_path.exists():
            out_path.unlink()
        sys.exit(1)

    if not _validate_netcdf(str(out_path)):
        body_head = ""
        try:
            with open(out_path, "rb") as fh:
                body_head = fh.read(512).decode("utf-8", errors="replace")
        except Exception:
            pass
        print(
            "Response is not a netCDF file (magic bytes mismatch). "
            f"First 512 bytes:\n{body_head}",
            file=sys.stderr,
        )
        out_path.unlink()
        sys.exit(1)

    # Sanity-check with xarray
    import xarray as xr  # noqa: E402
    try:
        ds = xr.open_dataset(str(out_path), engine="scipy")
    except Exception as e:
        print(f"xarray failed to open downloaded file: {e}", file=sys.stderr)
        sys.exit(1)

    elev_var = None
    for name in ("elevation", "Elevation", "z", "Z", "bathymetry", "Band1"):
        if name in ds.variables:
            elev_var = name
            break
    if elev_var is None:
        print(
            f"Cannot find elevation variable. Available: {list(ds.variables)}",
            file=sys.stderr,
        )
        sys.exit(1)

    elev = ds[elev_var]
    print(f"Shape: {elev.shape}")
    print(f"Elevation min: {float(elev.min()):.1f} m")
    print(f"Elevation max: {float(elev.max()):.1f} m")

    # Provenance JSON
    size_bytes = out_path.stat().st_size
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    retrieved_at = datetime.now(timezone.utc).isoformat()

    prov = {
        "source_url": url,
        "bbox": [lat_min, lat_max, lon_min, lon_max],
        "sha256": sha,
        "size_bytes": size_bytes,
        "retrieved_at_utc": retrieved_at,
        "license": "GEBCO 2025 grid, public domain attribution required",
    }
    prov_path = out_path.with_suffix(".json")
    prov_path.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    print(f"Provenance: {prov_path}")
    print(f"Output:     {out_path}")


if __name__ == "__main__":
    main()