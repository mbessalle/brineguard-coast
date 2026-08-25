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
    ny, nx = config["domain"]["ny"], config["domain"]["nx"]
    if ny < 20 or nx < 20:
        raise ValueError(f"Domain grid too small ({ny}x{nx}), need at least 20x20")
    if len(config["domain"]["outfalls"]) < 1:
        raise ValueError("At least one outfall is required")
    if len(config["domain"]["receptors"]) < 1:
        raise ValueError("At least one receptor is required")
    horizon = config["dispatch"]["horizon_hours"]
    if horizon not in {24, 48}:
        raise ValueError(f"dispatch.horizon_hours must be 24 or 48, got {horizon}")
    demand = config["dispatch"]["demand_m3_h"]
    tariff = config["dispatch"]["tariff"]
    if len(demand) != len(tariff):
        raise ValueError(f"demand_m3_h length ({len(demand)}) must equal tariff length ({len(tariff)})")
    if len(demand) < horizon:
        raise ValueError(f"demand_m3_h length ({len(demand)}) must be >= horizon_hours ({horizon})")
    receptor_names = {r["name"] for r in config["domain"]["receptors"]}
    plant_keys = {"name", "min_m3_h", "max_m3_h", "recovery", "brine_salinity_anomaly_kg_m3",
                  "energy_kwh_m3", "ramp_m3_h_per_h", "initial_m3_h"}
    for plant in config["dispatch"]["plants"]:
        if missing_keys := plant_keys - plant.keys():
            raise ValueError(f"Plant {plant.get('name', '?')} missing keys: {sorted(missing_keys)}")
        if "local_receptors" in plant:
            for rname in plant["local_receptors"]:
                if rname not in receptor_names:
                    raise ValueError(
                        f"Plant {plant['name']}: local_receptor '{rname}' not in domain.receptors"
                    )
    if "ramp_weight" not in config["dispatch"]:
        raise ValueError("dispatch.ramp_weight is required")
    if "currents" in config["domain"]:
        cur = config["domain"]["currents"]
        if cur["type"] not in {"steady", "tidal"}:
            raise ValueError(f"domain.currents.type must be steady or tidal, got {cur['type']}")
        for field in ("u_mean_m_s", "v_mean_m_s"):
            if not isinstance(cur.get(field), (int, float)):
                raise ValueError(f"domain.currents.{field} must be numeric")
        if cur["type"] == "tidal":
            for field in ("u_amp_m_s", "v_amp_m_s"):
                if not isinstance(cur.get(field), (int, float)):
                    raise ValueError(f"domain.currents.{field} must be numeric")
            if not isinstance(cur.get("period_h"), (int, float)) or cur["period_h"] <= 0:
                raise ValueError(f"domain.currents.period_h must be > 0, got {cur.get('period_h')}")
            cur.setdefault("period_h", 12.42)
            cur.setdefault("phase_h", 0.0)
            cur.setdefault("t0_h", 0.0)
    if "rolling" in config:
        r = config["rolling"]
        enact = r.get("enact_hours")
        if not isinstance(enact, int) or enact < 1 or enact >= horizon:
            raise ValueError(
                f"rolling.enact_hours ({enact}) must be 1 <= enact_hours < horizon_hours ({horizon})"
            )
        if r.get("total_hours") != len(demand):
            raise ValueError(
                f"rolling.total_hours ({r.get('total_hours')}) must equal len(demand_m3_h) ({len(demand)})"
            )
    return config
