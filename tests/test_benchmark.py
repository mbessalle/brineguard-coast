from __future__ import annotations

import json
from pathlib import Path

from brineguard.experiments.benchmark import run_benchmark


def test_benchmark_on_first_slice_flex4(tmp_path):
    """Reduced benchmark: single config, 24h, flex4 only."""
    output_root = tmp_path / "runs"
    run_benchmark(
        config_paths=["configs/first_slice.yaml"],
        run_id="test-bench",
        output_root=str(output_root),
        flex_scenarios=("flex4",),
    )
    run_dir = output_root / "test-bench"
    assert run_dir.is_dir()

    # comparison.json structure and required keys.
    with (run_dir / "comparison.json").open() as fh:
        data = json.load(fh)
    cells = data["cells"]
    assert "first_slice/flex4" in cells
    cell = cells["first_slice/flex4"]
    strategies = cell["strategies"]
    required = {"A", "B_capacity", "B_cost", "C", "C_matched_capacity", "C_matched_cost"}
    assert required == set(strategies.keys()), f"Missing strategies: {required - set(strategies.keys())}"

    # Identical config sha256 across strategies.
    sha_set = {s["config_sha256"] for s in strategies.values()}
    assert len(sha_set) == 1, f"Non-identical sha256: {sha_set}"

    # Matched C energy_cost <= B energy_cost + tolerance.
    for rule in ("capacity", "cost"):
        b_key, c_key = f"B_{rule}", f"C_matched_{rule}"
        if strategies[c_key].get("benefit_null"):
            continue
        b_cost = strategies[b_key]["energy_cost"]
        c_cost = strategies[c_key]["energy_cost"]
        assert c_cost <= b_cost + 1e-6, (
            f"C_matched_{rule} cost {c_cost} exceeds B_{rule} cost {b_cost}"
        )

    # A/B/C water-balance audits with zero violations.
    for s in ("A", "B_capacity", "B_cost", "C"):
        if s in strategies:
            assert strategies[s]["audit_pass"], f"{s} audit failed: {strategies[s].get('audit_violations')}"

    # Figure file exists and is non-empty.
    fig_path = run_dir / "figures" / "coordination_benefit.png"
    assert fig_path.exists()
    assert fig_path.stat().st_size > 0

    # CSV exists.
    assert (run_dir / "comparison.csv").exists()

    # Manifest exists.
    assert (run_dir / "manifest.json").exists()