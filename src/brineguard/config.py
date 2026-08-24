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
    return config
