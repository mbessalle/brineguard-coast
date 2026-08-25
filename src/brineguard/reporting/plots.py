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


def _empty_figure(output_dir: Path, name: str, message: str) -> Path:
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.text(0.5, 0.5, message, ha="center", va="center", transform=ax.transAxes)
    path = output_dir / "figures" / name
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def uncertainty_intervals_figure(output_dir: Path) -> Path:
    """Per-strategy p5–p95 exposure interval bars with p50 median markers."""
    data_path = output_dir / "ensemble.json"
    if not data_path.exists():
        return _empty_figure(output_dir, "uncertainty_intervals.png", "No ensemble data")
    with data_path.open() as fh:
        data = json.load(fh)
    strategies = data["strategies"]
    names = [s for s in strategies if "held_out" in strategies[s]]
    if not names:
        return _empty_figure(output_dir, "uncertainty_intervals.png", "No valid strategies")
    p5 = np.array([strategies[s]["held_out"]["p5"] for s in names])
    p50 = np.array([strategies[s]["held_out"]["p50"] for s in names])
    p95 = np.array([strategies[s]["held_out"]["p95"] for s in names])
    y = np.arange(len(names))
    fig, ax = plt.subplots(figsize=(9, max(3, 0.6 * len(names))))
    ax.errorbar(p50, y, xerr=[p50 - p5, p95 - p50], fmt="o", capsize=4,
                color="tab:blue", ecolor="gray", elinewidth=1.5)
    ax.set_yticks(y)
    ax.set_yticklabels(names)
    ax.set_xlabel("Exposure sum (m²·kg/m³·h)")
    ax.set_title("Held-out exposure uncertainty by strategy (p5–p95, median marker)")
    fig.tight_layout()
    path = output_dir / "figures" / "uncertainty_intervals.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def pareto_frontier_figure(output_dir: Path) -> Path:
    """Cost vs exposure Pareto curve; infeasible caps marked."""
    data_path = output_dir / "sensitivity.json"
    if not data_path.exists():
        return _empty_figure(output_dir, "pareto_frontier.png", "No sensitivity data")
    with data_path.open() as fh:
        data = json.load(fh)
    frontier = data.get("pareto_frontier", [])
    if not frontier:
        return _empty_figure(output_dir, "pareto_frontier.png", "Empty Pareto frontier")
    feasible = [r for r in frontier if r.get("feasible")]
    infeasible = [r for r in frontier if not r.get("feasible")]
    fig, ax = plt.subplots(figsize=(9, 6))
    if feasible:
        xs = [r["energy_cost"] for r in feasible]
        ys = [r["exposure_sum"] for r in feasible]
        ax.plot(xs, ys, marker="o", label="feasible")
    if infeasible:
        caps = [r["cost_cap"] for r in infeasible]
        ymin = min((r["exposure_sum"] for r in feasible), default=0.0)
        ax.scatter(caps, [ymin] * len(caps), marker="x", color="red", s=80,
                   label="infeasible")
    ax.set_xlabel("Energy cost")
    ax.set_ylabel("Exposure sum (m²·kg/m³·h)")
    ax.set_title("Cost–exposure Pareto frontier")
    ax.legend()
    fig.tight_layout()
    path = output_dir / "figures" / "pareto_frontier.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path


def sensitivity_benefit_figure(output_dir: Path) -> Path:
    """Coordination benefit by axis/value, one panel per sweep axis."""
    data_path = output_dir / "sensitivity.json"
    if not data_path.exists():
        return _empty_figure(output_dir, "sensitivity_benefit.png", "No sensitivity data")
    with data_path.open() as fh:
        data = json.load(fh)
    sweep = data.get("sensitivity_sweep", [])
    axes = ["storage_scale", "turndown", "dispersion_scale"]
    fig, axs = plt.subplots(1, 3, figsize=(15, 4))
    for ax, axis in zip(axs, axes):
        pts = [r for r in sweep if r.get("axis") == axis and r.get("feasible")]
        if pts:
            xs = [r["value"] for r in pts]
            ys = [r["benefit"] for r in pts]
            ax.plot(xs, ys, marker="o")
        else:
            ax.text(0.5, 0.5, "no feasible points", ha="center", va="center",
                    transform=ax.transAxes)
        ax.set_title(axis)
        ax.set_xlabel("value")
        ax.set_ylabel("coordination benefit")
    fig.tight_layout()
    path = output_dir / "figures" / "sensitivity_benefit.png"
    fig.savefig(path, dpi=160)
    plt.close(fig)
    return path
