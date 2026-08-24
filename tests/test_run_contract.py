from pathlib import Path
import yaml

from brineguard.config import load_config
from brineguard.experiments.runner import run


def test_saved_config_emits_complete_run_contract(tmp_path):
    config = load_config("configs/first_slice.yaml")
    config["run"]["output_root"] = str(tmp_path / "runs")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    run_dir = run(config_path)
    expected = {
        "manifest.json", "config.resolved.yaml", "environment.json", "inputs.json",
        "schedule.parquet", "storage.parquet", "receptor_salinity.zarr",
        "spatial_summary.nc", "metrics.csv", "metrics.json", "solver.json",
        "validation.json", "figures", "report.html",
    }
    assert expected == {path.name for path in run_dir.iterdir()}
    assert (run_dir / "figures" / "optimized_vs_constant.png").stat().st_size > 0
