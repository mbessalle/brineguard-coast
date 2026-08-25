#!/usr/bin/env python3
"""Copernicus Marine currents fetcher — subset a named CMEMS dataset to a bounding box.

Requires the ``copernicusmarine`` Python package and valid credentials
(COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD env vars
or ~/.copernicusmarine config).  When either is missing the script prints
precise setup instructions and exits with code 2 — this is the expected
outcome when credentials have not been provisioned.

Usage:
  python3 tools/fetch_cmems.py --dataset-id cmems_obs-sl_glo_phy-ssh_my_allsat-l4-duacs-0.25deg_P1D ...

For Red Sea hourly currents see the Copernicus Marine Data Store:
  https://data.marine.copernicus.eu
Look for product IDs containing "REDSEA" or filtering by
region = "Red Sea", variable = "sea_water_velocity".
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _check_package() -> bool:
    try:
        import copernicusmarine  # noqa: F401
        return True
    except ImportError:
        return False


def _check_credentials() -> bool:
    if os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME") and os.environ.get(
        "COPERNICUSMARINE_SERVICE_PASSWORD"
    ):
        return True
    cfg = Path.home() / ".copernicusmarine" / ".copernicusmarine-credentials"
    if cfg.exists():
        return True
    return False


def _setup_instructions() -> str:
    return (
        "The copernicusmarine package is not installed or credentials are missing.\n"
        "\n"
        "Setup steps:\n"
        "  1. pip install copernicusmarine\n"
        "  2. copernicusmarine login\n"
        "     (create a free account at https://data.marine.copernicus.eu first)\n"
        "\n"
        "Alternatively, set environment variables:\n"
        "  export COPERNICUSMARINE_SERVICE_USERNAME=<your_username>\n"
        "  export COPERNICUSMARINE_SERVICE_PASSWORD=<your_password>\n"
    )


def _fetch(
    dataset_id: str,
    bbox: tuple[float, float, float, float],
    start: str,
    end: str,
    output_dir: Path,
) -> None:
    import copernicusmarine as cm  # noqa: E402

    lat_min, lat_max, lon_min, lon_max = bbox
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Fetching {dataset_id} for {bbox} [{start} .. {end}] …", file=sys.stderr)
    result = cm.subset(
        dataset_id=dataset_id,
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        start_datetime=start,
        end_datetime=end,
        output_directory=str(output_dir),
        force_download=True,
    )

    out_path = Path(result.file_path) if hasattr(result, "file_path") else None
    if out_path is None:
        # Fallback: look for the newest netCDF in output dir
        ncs = sorted(output_dir.glob("*.nc"), key=lambda p: p.stat().st_mtime)
        out_path = ncs[-1] if ncs else None

    if out_path is None:
        print("Subset completed but could not locate output file.", file=sys.stderr)
        sys.exit(1)

    # Provenance
    import hashlib
    import json
    from datetime import datetime, timezone

    size_bytes = out_path.stat().st_size
    sha = hashlib.sha256(out_path.read_bytes()).hexdigest()
    retrieved_at = datetime.now(timezone.utc).isoformat()

    prov = {
        "source": "Copernicus Marine Service (CMEMS)",
        "dataset_id": dataset_id,
        "bbox": [lat_min, lat_max, lon_min, lon_max],
        "time_window": [start, end],
        "sha256": sha,
        "size_bytes": size_bytes,
        "retrieved_at_utc": retrieved_at,
        "license": (
            "CMEMS — free registration required; see "
            "https://marine.copernicus.eu/user-corner/service-commitments"
        ),
    }
    prov_path = out_path.with_suffix(".json")
    prov_path.write_text(json.dumps(prov, indent=2) + "\n", encoding="utf-8")
    print(f"Output:     {out_path}")
    print(f"Provenance: {prov_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copernicus Marine currents fetcher — subset a CMEMS dataset.",
    )
    parser.add_argument(
        "--dataset-id", required=True,
        help="CMEMS dataset ID (e.g. cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m). "
             "Browse https://data.marine.copernicus.eu to find the right product.",
    )
    parser.add_argument(
        "--bbox", nargs=4, type=float, required=True,
        metavar=("LAT_MIN", "LAT_MAX", "LON_MIN", "LON_MAX"),
    )
    parser.add_argument(
        "--start", required=True,
        help="Start datetime (ISO format, e.g. 2024-01-01T00:00:00).",
    )
    parser.add_argument(
        "--end", required=True,
        help="End datetime (ISO format).",
    )
    parser.add_argument(
        "-o", "--output-dir", default=None,
        help="Output directory (default: data/registry/cmems/).",
    )
    args = parser.parse_args()

    pkg_ok = _check_package()
    creds_ok = _check_credentials()

    if not pkg_ok or not creds_ok:
        print(_setup_instructions(), file=sys.stderr)
        sys.exit(2)

    lat_min, lat_max, lon_min, lon_max = args.bbox
    if lat_min >= lat_max:
        parser.error("LAT_MIN must be < LAT_MAX")
    if lon_min >= lon_max:
        parser.error("LON_MIN must be < LON_MAX")

    out_dir = Path(args.output_dir) if args.output_dir else Path("data/registry/cmems")

    _fetch(
        dataset_id=args.dataset_id,
        bbox=(lat_min, lat_max, lon_min, lon_max),
        start=args.start,
        end=args.end,
        output_dir=out_dir,
    )


if __name__ == "__main__":
    main()