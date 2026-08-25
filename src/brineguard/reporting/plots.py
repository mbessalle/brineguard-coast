import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import xarray as xr


def comparison_figure(run_dir: Path) -> Path:
    schedule = pd.read_parquet(run_dir / "schedule.parquet")
    salinity = xr.open_zarr(run_dir / "receptor_salinity.zarr", consolidated=False)
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


def coordination_benefit_figure(output_dir: Path) -> Path:
    """Bar chart of coordination benefit per cell/rule from benchmark comparison.json."""
    data_path = output_dir / "comparison.json"
    if not data_path.exists():
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "No benchmark data", ha="center", va="center", transform=ax.transAxes)
        path = output_dir / "figures" / "coordination_benefit.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        return path
    with data_path.open() as fh:
        cells = json.load(fh)["cells"]
    rows: list[dict] = []
    for cell_key, cell in cells.items():
        strategies = cell.get("strategies", {})
        for rule in ("capacity", "cost"):
            ckey = f"C_matched_{rule}"
            if ckey in strategies and not strategies[ckey].get("benefit_null"):
                rows.append({
                    "cell": cell_key, "rule": rule,
                    "benefit": float(strategies[ckey].get("coordination_benefit", 0)),
                })
    if not rows:
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.text(0.5, 0.5, "No valid coordination benefits", ha="center", va="center",
                transform=ax.transAxes)
        path = output_dir / "figures" / "coordination_benefit.png"
        fig.savefig(path, dpi=160)
        plt.close(fig)
        return path
    df = pd.DataFrame(rows)
    pivot = df.pivot_table(values="benefit", index="cell", columns="rule", aggfunc="first")
    fig, ax = plt.subplots(figsize=(max(8, len(pivot) * 1.5), 5))
    x = np.arange(len(pivot))
    width = 0.35
    for idx, rule in enumerate(["capacity", "cost"]):
        vals = pivot[rule].values if rule in pivot.columns else np.zeros(len(pivot))
        ax.bar(x + idx * width, vals, width, label=f"B_{rule}")
    ax.set_xticks(x + width / 2)
    ax.set_xticklabels(pivot.index, rotation=30, ha="right", fontsize=8)
    ax.set_ylabel("Coordination benefit")
    ax.set_title("Coordination Benefit (exposure reduction vs independent)")
    ax.legend()
    ax.axhline(0, color="gray", linewidth=0.8)
    fig.tight_layout()
    path = output_dir / "figures" / "coordination_benefit.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
