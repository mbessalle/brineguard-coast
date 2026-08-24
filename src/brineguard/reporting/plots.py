from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import xarray as xr


def comparison_figure(run_dir: Path) -> Path:
    schedule = pd.read_parquet(run_dir / "schedule.parquet")
    salinity = xr.open_zarr(run_dir / "receptor_salinity.zarr")
    fig, axes = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    for name, group in schedule.groupby("plant"):
        axes[0].plot(group["hour"], group["production_m3_h"], marker="o", label=name)
    axes[0].set_ylabel("Production (m³/h)")
    axes[0].legend(ncol=3)
    for receptor in salinity.receptor.values:
        axes[1].plot(salinity.hour, salinity.optimized.sel(receptor=receptor), label=str(receptor))
        axes[1].plot(salinity.hour, salinity.constant.sel(receptor=receptor), linestyle="--", alpha=.55)
    axes[1].set_ylabel("Salinity anomaly (kg/m³)")
    axes[1].set_xlabel("Hour")
    axes[1].set_title("Optimized (solid) vs constant-production reference (dashed)")
    axes[1].legend(ncol=2, fontsize=8)
    fig.tight_layout()
    path = run_dir / "figures" / "optimized_vs_constant.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
