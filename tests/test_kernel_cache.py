import copy

import numpy as np

from brineguard.config import load_config
from brineguard.transport.kernels import kernel_cache_key, load_or_build_kernel


def test_cache_roundtrip_hits_second_time_with_identical_kernel(tmp_path):
    config = load_config("configs/first_slice.yaml")
    kernel_first, info_first = load_or_build_kernel(config, tmp_path)
    assert info_first["cache_hit"] is False
    kernel_second, info_second = load_or_build_kernel(config, tmp_path)
    assert info_second["cache_hit"] is True
    assert info_second["cache_key"] == info_first["cache_key"]
    assert np.array_equal(kernel_first, kernel_second)


def test_cache_key_ignores_dispatch_economics():
    config = load_config("configs/first_slice.yaml")
    key = kernel_cache_key(config)

    tariff_changed = copy.deepcopy(config)
    tariff_changed["dispatch"]["tariff"] = [t * 2 for t in tariff_changed["dispatch"]["tariff"]]
    assert kernel_cache_key(tariff_changed) == key

    exposure_changed = copy.deepcopy(config)
    exposure_changed["dispatch"]["exposure_weight"] *= 10
    assert kernel_cache_key(exposure_changed) == key

    threshold_changed = copy.deepcopy(config)
    threshold_changed["domain"]["receptors"][0]["threshold_kg_m3"] *= 10
    assert kernel_cache_key(threshold_changed) == key


def test_cache_key_changes_with_transport_relevant_inputs():
    config = load_config("configs/first_slice.yaml")
    key = kernel_cache_key(config)

    dispersion_changed = copy.deepcopy(config)
    dispersion_changed["domain"]["dispersion_m2_s"] *= 2
    assert kernel_cache_key(dispersion_changed) != key

    velocity_changed = copy.deepcopy(config)
    velocity_changed["domain"]["velocity_m_s"] = [0.08, 0.0]
    assert kernel_cache_key(velocity_changed) != key

    receptor_position_changed = copy.deepcopy(config)
    receptor_position_changed["domain"]["receptors"][0]["row"] += 1
    assert kernel_cache_key(receptor_position_changed) != key
