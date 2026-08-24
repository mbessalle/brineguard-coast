import copy

import numpy as np
import pytest

from brineguard.config import load_config
from brineguard.transport.kernels import build_kernel, reconstruct
from brineguard.transport.solver import simulate
from brineguard.transport.validation import _refined_config, kernel_agreement


def test_kernel_agrees_with_direct_solver_within_declared_gates():
    config = load_config("configs/first_slice.yaml")
    kernel = build_kernel(config)
    loads = np.random.default_rng(3).uniform(0, 0.7, (24, 3))
    direct, _ = simulate(config, loads)
    result = kernel_agreement(config, direct, reconstruct(kernel, loads))
    assert result["kernel_agreement_pass"], result


def test_direct_solver_converges_toward_kernel_under_refinement():
    config = load_config("configs/first_slice.yaml")
    loads = np.random.default_rng(3).uniform(0, 0.7, (24, 3))
    kernel_dose = reconstruct(build_kernel(config), loads).sum(axis=0)
    base_gap = np.abs(simulate(config, loads)[0].sum(axis=0) - kernel_dose) / kernel_dose
    fine_gap = np.abs(simulate(_refined_config(config, 2), loads)[0].sum(axis=0) - kernel_dose) / kernel_dose
    assert np.all(fine_gap < 0.5 * base_gap), (base_gap, fine_gap)


def test_kernel_is_lag_stationary_under_constant_currents():
    config = load_config("configs/first_slice.yaml")
    kernel = build_kernel(config)
    hours = config["dispatch"]["horizon_hours"]
    for lag in (0, 1, 5, 12):
        reference = kernel[:, :, lag, 0]
        for release in range(1, hours - lag):
            assert np.allclose(kernel[:, :, release + lag, release], reference, rtol=1e-12)


def test_advection_dominated_configuration_raises():
    config = copy.deepcopy(load_config("configs/first_slice.yaml"))
    config["domain"]["velocity_m_s"] = [0.5, 0.0]
    loads = np.zeros((1, 3))
    with pytest.raises(ValueError, match="negative dispersion"):
        simulate(config, loads)
