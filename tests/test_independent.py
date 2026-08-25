import copy

import numpy as np

from brineguard.config import load_config
from brineguard.dispatch.independent import allocate, solve_independent
from brineguard.dispatch.model import solve_dispatch
from brineguard.dispatch.verify import audit_schedule
from brineguard.transport.kernels import build_kernel


def test_allocate_capacity_obligations_sum_to_demand():
    config = load_config("configs/first_slice.yaml")
    demand = np.asarray(config["dispatch"]["demand_m3_h"], dtype=float)
    alloc = allocate(config, "capacity")
    assert np.allclose(alloc["obligation_m3_h"].sum(axis=1), demand)
    assert np.isclose(alloc["storage_share"].sum(), 1.0)


def test_allocate_cost_obligations_sum_to_total_demand():
    config = load_config("configs/first_slice.yaml")
    demand = np.asarray(config["dispatch"]["demand_m3_h"], dtype=float)
    alloc = allocate(config, "cost")
    assert np.isclose(alloc["obligation_m3_h"].sum(), demand.sum())
    assert np.isclose(alloc["storage_share"].sum(), 1.0)


def test_independent_capacity_passes_audit():
    config = load_config("configs/first_slice.yaml")
    solution = solve_independent(config, build_kernel(config), "capacity")
    audit = audit_schedule(config, solution["production_m3_h"], solution["storage_m3"])
    assert audit["pass"], audit["violations"]
    assert audit["violation_count"] == 0


def test_independent_cost_passes_audit():
    config = load_config("configs/first_slice.yaml")
    solution = solve_independent(config, build_kernel(config), "cost")
    audit = audit_schedule(config, solution["production_m3_h"], solution["storage_m3"])
    assert audit["pass"], audit["violations"]
    assert audit["violation_count"] == 0


def test_local_receptor_isolation_matches_pure_cost_optimum():
    """Plant with local_receptors=[] should match cost-only optimum (no exposure bias)."""
    config = load_config("configs/first_slice.yaml")
    isolated_config = copy.deepcopy(config)
    isolated_config["dispatch"]["plants"][0]["local_receptors"] = []
    solution = solve_independent(isolated_config, build_kernel(isolated_config), "capacity")
    # Compare against independent solve with exposure_weight=0 (same obligation, no exposure).
    zero_exp = copy.deepcopy(config)
    zero_exp["dispatch"]["exposure_weight"] = 0.0
    ref = solve_independent(zero_exp, build_kernel(zero_exp), "capacity")
    assert np.allclose(solution["per_plant"][0]["production_m3_h"],
                       ref["per_plant"][0]["production_m3_h"], atol=1e-6)


def test_per_plant_storage_shares_sum_to_one_and_stay_within_scaled_bounds():
    config = load_config("configs/first_slice.yaml")
    for rule in ("capacity", "cost"):
        solution = solve_independent(config, build_kernel(config), rule)
        tank = config["dispatch"]["tank"]
        shares = [p["storage_share"] for p in solution["per_plant"]]
        assert np.isclose(sum(shares), 1.0)
        for pp in solution["per_plant"]:
            s = float(pp["storage_share"])
            assert np.all(pp["storage_m3"] >= tank["minimum_m3"] * s - 1e-6)
            assert np.all(pp["storage_m3"] <= tank["capacity_m3"] * s + 1e-6)


def test_independent_solutions_have_expected_keys():
    config = load_config("configs/first_slice.yaml")
    solution = solve_independent(config, build_kernel(config), "capacity")
    for key in ("production_m3_h", "storage_m3", "loads_kg_s", "objective",
                "energy_cost", "ramp_cost", "exposure_proxy", "rule", "per_plant"):
        assert key in solution
    assert solution["rule"] == "capacity"
    assert len(solution["per_plant"]) == len(config["dispatch"]["plants"])