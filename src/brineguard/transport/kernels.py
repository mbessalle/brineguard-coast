from __future__ import annotations

import numpy as np
from brineguard.transport.solver import simulate


def build_kernel(config: dict) -> np.ndarray:
    """Return H[receptor, source, arrival_hour, release_hour] per kg/s.

    Built from a single unit impulse per source at hour 0, then shifted in time
    (kernel[:, :, arrival, release] = lag[arrival - release]). This is only exact
    because the underlying `simulate`/`advance` transport is currently strictly
    time-invariant: velocity, dispersion, depth and the wet mask are all fixed
    scalars/fields for the whole horizon (see configs/first_slice.yaml). BUILD_PLAN
    5.2 requires H to be indexed by both release and arrival time specifically
    because forecast currents are meant to become nonstationary later; if/when the
    solver gains time-varying forcing, this shift-based construction must be
    replaced with one impulse simulation per release hour, or it will silently
    reconstruct the wrong receptor response with no current test able to catch it.
    """
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
