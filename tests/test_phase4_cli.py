"""Phase 4 T4 integration tests: CLI subcommands, hybrid wiring, objective
conditioning, and the between-plant synchronization metric.

Kept fast: first_slice (24h) config, 4 ensemble members, 3 Pareto points,
single flex4 benchmark cell.
"""

from __future__ import annotations

import copy
import json

import numpy as np

from brineguard.config import load_config
from brineguard.transport.kernels import build_kernel


# ---------------------------------------------------------------------------
# 1 — run-ensemble CLI artifacts
# ---------------------------------------------------------------------------

def test_run_ensemble_artifacts(tmp_path):
    from brineguard.experiments.ensemble import run_ensemble

    output = run_ensemble("configs/first_slice.yaml", "t-ens", n_members=4,
                          seed=7, output_root=str(tmp_path))
    data = json.loads((output / "ensemble.json").read_text())
    strategies = data["strategies"]
    assert set(strategies) == {"A", "B_capacity", "B_cost", "C"}

    for entry in strategies.values():
        assert len(entry["exposure_per_member"]) == 4
        assert set(entry["held_out"]) == {"mean", "std", "p5", "p50", "p95"}
        assert entry["held_out"]["p5"] <= entry["held_out"]["p50"] <= entry["held_out"]["p95"]

    for rule in ("B_capacity", "B_cost"):
        assert len(strategies[rule]["benefit_distribution"]) == 4
        assert np.isfinite(strategies[rule]["benefit_nominal"])
        assert set(strategies[rule]["benefit_held_out"]) == {"mean", "std", "p5", "p50", "p95"}

    assert len(data["member_metadata"]) == 4
    assert data["member_metadata"][0] == {"index": 0, "clipped": False}

    fig = output / "figures" / "uncertainty_intervals.png"
    assert fig.exists() and fig.stat().st_size > 0

    manifest = json.loads((output / "manifest.json").read_text())
    assert {"run_id", "created_utc", "git_revision", "config_sha256"} <= set(manifest)


# ---------------------------------------------------------------------------
# 2 — run-sensitivity CLI artifacts
# ---------------------------------------------------------------------------

def test_run_sensitivity_artifacts(tmp_path):
    from brineguard.experiments.sensitivity import run_sensitivity

    output = run_sensitivity("configs/first_slice.yaml", "t-sens", n_points=3,
                             output_root=str(tmp_path))
    data = json.loads((output / "sensitivity.json").read_text())

    frontier = data["pareto_frontier"]
    assert len(frontier) == 3
    assert all(r["feasible"] for r in frontier), frontier

    sweep = data["sensitivity_sweep"]
    assert sweep
    required = {"axis", "value", "benefit", "exposure_B", "exposure_C", "energy_cost_B"}
    for rec in sweep:
        assert required <= set(rec.keys()), rec

    fig1 = output / "figures" / "pareto_frontier.png"
    fig2 = output / "figures" / "sensitivity_benefit.png"
    assert fig1.exists() and fig1.stat().st_size > 0
    assert fig2.exists() and fig2.stat().st_size > 0

    manifest = json.loads((output / "manifest.json").read_text())
    assert {"run_id", "created_utc", "git_revision", "config_sha256"} <= set(manifest)


# ---------------------------------------------------------------------------
# 3 — CLI subcommands parse and dispatch
# ---------------------------------------------------------------------------

def test_cli_subcommands_parse_and_dispatch(monkeypatch, tmp_path):
    import sys

    from brineguard.cli import main

    runs = tmp_path / "runs"

    monkeypatch.setattr(sys, "argv", [
        "brineguard", "run-ensemble", "-c", "configs/first_slice.yaml",
        "--members", "4", "--run-id", "cli-ens", "--output-root", str(runs),
    ])
    main()
    assert (runs / "cli-ens" / "ensemble.json").exists()

    monkeypatch.setattr(sys, "argv", [
        "brineguard", "run-sensitivity", "-c", "configs/first_slice.yaml",
        "--n-points", "3", "--run-id", "cli-sens", "--output-root", str(runs),
    ])
    main()
    assert (runs / "cli-sens" / "sensitivity.json").exists()


# ---------------------------------------------------------------------------
# 4 — hybrid kernel builds through the real wiring (no monkeypatch)
# ---------------------------------------------------------------------------

def test_hybrid_kernel_builds_without_monkeypatch():
    config = load_config("configs/hybrid_redsea.yaml")
    truncated = copy.deepcopy(config)
    truncated["dispatch"]["horizon_hours"] = 24

    kernel = build_kernel(truncated)
    n_rec = len(config["domain"]["receptors"])
    n_src = len(config["domain"]["outfalls"])
    assert kernel.shape == (n_rec, n_src, 24, 24)
    assert np.isfinite(kernel).all(), "kernel contains NaN/Inf"
    assert (kernel >= 0).all(), "kernel entries should be nonnegative"


# ---------------------------------------------------------------------------
# 5 — objective-scale regression: constant scaling leaves the schedule unchanged
# ---------------------------------------------------------------------------

def test_objective_scale_regression(monkeypatch):
    from brineguard.dispatch import model as model_module
    from brineguard.dispatch.model import solve_dispatch

    config = load_config("configs/first_slice.yaml")
    kernel = build_kernel(config)

    # "Before the change": scale forced to 1.0 via the module constant.
    monkeypatch.setattr(model_module, "OBJECTIVE_SCALE", 1.0)
    baseline = solve_dispatch(config, kernel)

    # "After the change": the shipped 1e-6 conditioning scale.
    monkeypatch.setattr(model_module, "OBJECTIVE_SCALE", 1e-6)
    scaled = solve_dispatch(config, kernel)

    assert np.allclose(baseline["production_m3_h"], scaled["production_m3_h"], atol=1e-6)
    # Reported objective stays on the raw (unscaled) expression scale.
    assert np.isclose(baseline["objective"], scaled["objective"], rtol=1e-9)
    assert np.isclose(baseline["energy_cost"], scaled["energy_cost"], rtol=1e-9)


# ---------------------------------------------------------------------------
# 6 — between-plant synchronization keys in a small benchmark cell
# ---------------------------------------------------------------------------

def test_between_plant_sync_keys_in_benchmark(tmp_path):
    from brineguard.experiments.benchmark import run_benchmark

    output = run_benchmark(["configs/first_slice.yaml"], "t-bench",
                           output_root=str(tmp_path), flex_scenarios=("flex4",))
    data = json.loads((output / "comparison.json").read_text())
    dump = data["cells"]["first_slice/flex4"]["coincidental_dumping"]

    for key in ("B_capacity_vs_C", "B_cost_vs_C"):
        metrics = dump[key]
        assert "between_plant_sync_B" in metrics, key
        assert "between_plant_sync_C" in metrics, key
        for sync_key in ("between_plant_sync_B", "between_plant_sync_C"):
            assert np.isfinite(metrics[sync_key]), (key, sync_key)
            assert -1.0 <= metrics[sync_key] <= 1.0, (key, sync_key)
        # Per-plant B-vs-C correlations retained under their original key.
        assert "pearson_r" in metrics, key
        assert len(metrics["pearson_r"]) == 3
