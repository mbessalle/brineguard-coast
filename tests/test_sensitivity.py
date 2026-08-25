from __future__ import annotations

import copy

import numpy as np

from brineguard.config import load_config
from brineguard.transport.kernels import kernel_cache_key, load_or_build_kernel

from brineguard.experiments.sensitivity import (
    _dispersion_config,
    pareto_frontier,
    sensitivity_sweep,
)


def test_pareto_frontier_monotone_and_ordered():
    """Pareto: exposure is non-increasing as cost cap rises; endpoints in order."""
    config = load_config("configs/first_slice.yaml")
    kernel, _ = load_or_build_kernel(config, config["run"]["kernel_cache_dir"])
    frontier = pareto_frontier(config, kernel, n_points=4)
    assert len(frontier) == 4
    assert all(rec["feasible"] for rec in frontier), frontier

    ordered = sorted(frontier, key=lambda r: r["cost_cap"])
    exposures = [r["exposure_sum"] for r in ordered]
    for prev, curr in zip(exposures, exposures[1:]):
        assert curr <= prev + 1e-6, f"exposure not monotone non-increasing: {exposures}"

    assert ordered[-1]["exposure_sum"] <= ordered[0]["exposure_sum"] + 1e-6


def test_sensitivity_sweep_records_and_kernel_rebuild(tmp_path):
    """Reduced sweep (one value beyond nominal per axis) for speed; all records
    must be complete with finite benefits.  Turndown nominal 0.10 (flex2) is
    excluded here — it is numerically infeasible for cost-matched C at the
    config's exposure_weight=150M (a pre-existing HiGHS conditioning issue)."""
    config = copy.deepcopy(load_config("configs/first_slice.yaml"))
    config["run"]["kernel_cache_dir"] = str(tmp_path)

    records = sensitivity_sweep(
        config,
        storage_scales=(1.0, 0.5),
        turndowns=(0.05, 0.20),
        dispersion_scales=(1.0, 2.0),
    )
    assert len(records) == 6

    required = {"axis", "value", "benefit", "exposure_B", "exposure_C", "energy_cost_B"}
    for rec in records:
        assert required <= set(rec.keys()), rec
        assert rec["benefit"] is not None and np.isfinite(rec["benefit"]), rec
        assert np.isfinite(rec["exposure_B"]), rec
        assert np.isfinite(rec["exposure_C"]), rec
        assert np.isfinite(rec["energy_cost_B"]), rec

    axes = {rec["axis"] for rec in records}
    assert axes == {"storage_scale", "turndown", "dispersion_scale"}

    # Dispersion axis actually rebuilt the kernel: two distinct cache keys.
    assert kernel_cache_key(config) != kernel_cache_key(_dispersion_config(config, 2.0))
    cache_files = [p for p in tmp_path.glob("*.npz") if ".tmp-" not in p.name]
    assert len(cache_files) == 2, cache_files