from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import time

import numpy as np
import pandas as pd
import pyomo
import scipy
import xarray as xr
import yaml

from brineguard.config import load_config
from brineguard.dispatch.model import constant_schedule, solve_dispatch
from brineguard.dispatch.verify import audit_schedule
from brineguard.domain import generate_domain
from brineguard.reporting.plots import comparison_figure
from brineguard.transport.kernels import load_or_build_kernel, reconstruct
from brineguard.transport.solver import simulate
from brineguard.transport.validation import kernel_agreement, validate_transport


def _json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def run(config_path: str | Path, run_id: str | None = None) -> Path:
    started = time.monotonic()
    config_path = Path(config_path).resolve()
    config = load_config(config_path)
    run_id = run_id or config["run"]["id"]
    run_dir = Path(config["run"]["output_root"]) / run_id
    if run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {run_dir}; choose --run-id")
    (run_dir / "figures").mkdir(parents=True)
    (run_dir / "config.resolved.yaml").write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    validation = validate_transport(config)
    if not validation["transport_pass"]:
        raise RuntimeError(f"Transport validation failed: {validation}")
    kernel, kernel_cache = load_or_build_kernel(config, config["run"]["kernel_cache_dir"])
    solution = solve_dispatch(config, kernel)
    baseline = constant_schedule(config)
    audits = {"optimized": audit_schedule(config, solution["production_m3_h"], solution["storage_m3"]),
              "constant": audit_schedule(config, baseline["production_m3_h"], baseline["storage_m3"])}
    validation["dispatch_audit"] = audits
    validation["dispatch_audit_pass"] = all(audit["pass"] for audit in audits.values())
    if not validation["dispatch_audit_pass"]:
        raise RuntimeError(f"Water-balance audit failed: { {k: v['violations'] for k, v in audits.items()} }")
    direct, fields = simulate(config, solution["loads_kg_s"], record_full=True)
    reconstructed = reconstruct(kernel, solution["loads_kg_s"])
    replay = kernel_agreement(config, direct, reconstructed)
    validation["schedule_replay"] = replay["kernel_agreement"]
    validation["schedule_replay_pass"] = replay["kernel_agreement_pass"]
    validation["schedule_replay_max_abs_error_kg_m3"] = float(np.max(np.abs(direct - reconstructed)))
    if not validation["schedule_replay_pass"]:
        raise RuntimeError(f"Optimized-schedule replay validation failed: {replay}")
    hours = np.arange(config["dispatch"]["horizon_hours"])
    plant_names = [p["name"] for p in config["dispatch"]["plants"]]
    schedule = pd.DataFrame([
        {"hour": t, "plant": plant_names[i], "production_m3_h": solution["production_m3_h"][t, i],
         "brine_load_kg_s": solution["loads_kg_s"][t, i]}
        for t in hours for i in range(len(plant_names))
    ])
    schedule.to_parquet(run_dir / "schedule.parquet", index=False)
    pd.DataFrame({"hour": hours, "storage_m3": solution["storage_m3"],
                  "storage_constant_m3": baseline["storage_m3"],
                  "demand_m3_h": config["dispatch"]["demand_m3_h"]}).to_parquet(run_dir / "storage.parquet", index=False)
    constant, _ = simulate(config, baseline["loads_kg_s"])
    receptor_names = [r["name"] for r in config["domain"]["receptors"]]
    salinity = xr.Dataset({
        "optimized": (("hour", "receptor"), direct), "kernel_reconstruction": (("hour", "receptor"), reconstructed),
        "constant": (("hour", "receptor"), constant),
    }, coords={"hour": hours, "receptor": receptor_names}, attrs={"units": "kg m-3 salinity anomaly"})
    salinity.to_zarr(run_dir / "receptor_salinity.zarr", mode="w", consolidated=False)
    domain = generate_domain(config)
    xr.Dataset({"maximum_anomaly": (("y", "x"), fields.max(axis=0)),
                "cumulative_anomaly_hours": (("y", "x"), fields.sum(axis=0))}, coords=domain.coords,
               attrs={"provenance": "direct optimized-schedule transport replay"}).to_netcdf(run_dir / "spatial_summary.nc")
    metrics = {
        "objective": solution["objective"], "energy_cost": solution["energy_cost"],
        "ramp_cost": solution["ramp_cost"], "constant_energy_cost": baseline["energy_cost"],
        "exposure_proxy_m2_kg_m3_h": solution["exposure_proxy"],
        "maximum_receptor_anomaly_kg_m3": float(direct.max()),
        "constant_maximum_receptor_anomaly_kg_m3": float(constant.max()),
        "water_produced_m3": float(solution["production_m3_h"].sum()),
        "demand_served_m3": float(sum(config["dispatch"]["demand_m3_h"])),
    }
    pd.DataFrame([{"metric": key, "value": value} for key, value in metrics.items()]).to_csv(run_dir / "metrics.csv", index=False)
    _json(run_dir / "metrics.json", metrics)
    _json(run_dir / "solver.json", {"solver": solution["solver"], "termination_condition": solution["termination_condition"]})
    _json(run_dir / "validation.json", validation)
    git_revision = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=False).stdout.strip() or "unknown"
    config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
    _json(run_dir / "inputs.json", {"config": str(config_path), "config_sha256": config_sha,
                                    "kernel_cache": kernel_cache, "external_inputs": []})
    _json(run_dir / "environment.json", {"python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
          "scipy": scipy.__version__, "xarray": xr.__version__, "pyomo": pyomo.__version__})
    comparison_figure(run_dir)
    (run_dir / "report.html").write_text(
        "<!doctype html><meta charset='utf-8'><title>BrineGuard first slice</title>"
        "<h1>BrineGuard Coast — offline first slice</h1><p>Synthetic screening fixture; not a calibrated plume forecast.</p>"
        "<img src='figures/optimized_vs_constant.png' alt='optimized versus constant comparison'>",
        encoding="utf-8")
    _json(run_dir / "manifest.json", {"run_id": run_id, "created_utc": datetime.now(timezone.utc).isoformat(),
          "git_revision": git_revision, "seed": config["run"]["seed"], "config_sha256": config_sha,
          "duration_seconds": round(time.monotonic() - started, 3), "status": "complete"})
    return run_dir
