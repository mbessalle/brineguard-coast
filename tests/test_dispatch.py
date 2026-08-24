import numpy as np

from brineguard.config import load_config
from brineguard.dispatch.model import solve_dispatch
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
