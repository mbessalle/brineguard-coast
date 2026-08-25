import numpy as np

from brineguard.config import load_config
from brineguard.dispatch.model import constant_schedule, solve_dispatch
from brineguard.dispatch.verify import audit_schedule
from brineguard.transport.kernels import build_kernel


def test_dispatch_serves_demand_and_preserves_terminal_storage():
    config = load_config("configs/first_slice.yaml")
    solution = solve_dispatch(config, build_kernel(config))
    demand = np.asarray(config["dispatch"]["demand_m3_h"])
    production = solution["production_m3_h"].sum(axis=1)
    initial = config["dispatch"]["tank"]["initial_m3"]
    expected_storage = initial + np.cumsum(production - demand)
    assert np.allclose(solution["storage_m3"], expected_storage)
    assert np.isclose(solution["storage_m3"][-1], config["dispatch"]["tank"]["terminal_m3"])
    assert np.isclose(solution["production_m3_h"].sum(), demand.sum())
    assert solution["termination_condition"] == "optimal"


def test_optimized_solution_respects_ramp_limits():
    config = load_config("configs/first_slice.yaml")
    solution = solve_dispatch(config, build_kernel(config))
    production = solution["production_m3_h"]
    plants = config["dispatch"]["plants"]
    for i, plant in enumerate(plants):
        limit = plant["ramp_m3_h_per_h"]
        assert abs(production[0, i] - plant["initial_m3_h"]) <= limit + 1e-6
        for t in range(1, config["dispatch"]["horizon_hours"]):
            assert abs(production[t, i] - production[t - 1, i]) <= limit + 1e-6


def test_optimized_solution_passes_audit():
    config = load_config("configs/first_slice.yaml")
    solution = solve_dispatch(config, build_kernel(config))
    audit = audit_schedule(config, solution["production_m3_h"], solution["storage_m3"])
    assert audit["pass"], audit["violations"]
    assert audit["violations"] == {}


def test_constant_schedule_is_capacity_proportional_and_passes_audit():
    config = load_config("configs/first_slice.yaml")
    baseline = constant_schedule(config)
    production = baseline["production_m3_h"]

    assert np.allclose(production, production[0])

    plants = config["dispatch"]["plants"]
    capacities = np.array([p["max_m3_h"] for p in plants])
    assert np.allclose(production[0] / capacities, production[0, 0] / capacities[0])

    assert np.isclose(baseline["storage_m3"][-1], config["dispatch"]["tank"]["terminal_m3"])

    audit = audit_schedule(config, production, baseline["storage_m3"])
    assert audit["pass"], audit["violations"]
    assert audit["violation_count"] == 0


def test_audit_schedule_catches_production_above_maximum():
    config = load_config("configs/first_slice.yaml")
    baseline = constant_schedule(config)
    production = baseline["production_m3_h"].copy()
    production[0, 0] = config["dispatch"]["plants"][0]["max_m3_h"] + 100
    audit = audit_schedule(config, production, baseline["storage_m3"])
    assert not audit["pass"]
    assert "production_above_maximum_max_m3_h" in audit["violations"]


def test_audit_schedule_catches_storage_recursion_violation():
    config = load_config("configs/first_slice.yaml")
    baseline = constant_schedule(config)
    storage = baseline["storage_m3"].copy()
    storage[5] += 500
    audit = audit_schedule(config, baseline["production_m3_h"], storage)
    assert not audit["pass"]
    assert "storage_recursion_max_abs_error_m3" in audit["violations"]


def test_series_longer_than_horizon_slices_cleanly():
    import copy
    from brineguard.dispatch.verify import audit_schedule
    config = copy.deepcopy(load_config("configs/first_slice.yaml"))
    config["dispatch"]["demand_m3_h"] = config["dispatch"]["demand_m3_h"] * 4
    config["dispatch"]["tariff"] = config["dispatch"]["tariff"] * 4
    from brineguard.dispatch.model import constant_schedule
    result = constant_schedule(config)
    assert result["production_m3_h"].shape[0] == config["dispatch"]["horizon_hours"]
    audit = audit_schedule(config, result["production_m3_h"], result["storage_m3"])
    assert audit["pass"], audit["violations"]
