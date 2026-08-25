from __future__ import annotations

from pathlib import Path
import yaml


def load_config(path: str | Path) -> dict:
    path = Path(path)
    with path.open(encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    required = {"run", "domain", "dispatch", "validation"}
    missing = required - config.keys()
    if missing:
        raise ValueError(f"Missing config sections: {sorted(missing)}")
    if (config["domain"]["ny"], config["domain"]["nx"]) != (40, 60):
        raise ValueError("The first implementation slice requires a 40x60 grid")
    if len(config["domain"]["outfalls"]) != 3 or len(config["domain"]["receptors"]) != 4:
        raise ValueError("The first slice requires exactly three outfalls and four receptors")
    if config["dispatch"]["horizon_hours"] != 24:
        raise ValueError("The first slice requires a 24-hour horizon")
    plant_keys = {"name", "min_m3_h", "max_m3_h", "recovery", "brine_salinity_anomaly_kg_m3",
                  "energy_kwh_m3", "ramp_m3_h_per_h", "initial_m3_h"}
    for plant in config["dispatch"]["plants"]:
        if missing_keys := plant_keys - plant.keys():
            raise ValueError(f"Plant {plant.get('name', '?')} missing keys: {sorted(missing_keys)}")
    if "ramp_weight" not in config["dispatch"]:
        raise ValueError("dispatch.ramp_weight is required")
    return config
