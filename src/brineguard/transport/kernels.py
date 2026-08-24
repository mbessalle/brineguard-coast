from __future__ import annotations

import numpy as np
from brineguard.transport.solver import simulate


def build_kernel(config: dict) -> np.ndarray:
    """Return H[receptor, source, arrival_hour, release_hour] per kg/s."""
    hours = config["dispatch"]["horizon_hours"]
    n_sources = len(config["domain"]["outfalls"])
    n_receptors = len(config["domain"]["receptors"])
    lag = np.zeros((hours, n_sources, n_receptors))
    for source in range(n_sources):
        loads = np.zeros((hours, n_sources))
        loads[0, source] = 1.0
        lag[:, source, :], _ = simulate(config, loads)
    kernel = np.zeros((n_receptors, n_sources, hours, hours))
    for release in range(hours):
        for arrival in range(release, hours):
            kernel[:, :, arrival, release] = lag[arrival - release].T
    return kernel


def reconstruct(kernel: np.ndarray, loads_kg_s: np.ndarray) -> np.ndarray:
    return np.einsum("rits,si->tr", kernel, loads_kg_s)
