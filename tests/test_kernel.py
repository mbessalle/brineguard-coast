import numpy as np
from brineguard.config import load_config
from brineguard.transport.kernels import build_kernel, reconstruct
from brineguard.transport.solver import simulate


def test_kernel_reconstructs_direct_solver():
    config = load_config("configs/first_slice.yaml")
    kernel = build_kernel(config)
    loads = np.random.default_rng(3).uniform(0, 0.7, (24, 3))
    direct, _ = simulate(config, loads)
    assert np.allclose(reconstruct(kernel, loads), direct, atol=1e-12)
