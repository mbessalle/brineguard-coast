#!/usr/bin/env python3
"""Aggregate dispatch_ledger.jsonl into per-route routing statistics.

Reads the ledger, groups by route, computes:
  n_dispatches, n_completed (wait_result rc==0), first_pass_rate,
  mean wait rc, mean cost_usd_delta.
Handles missing fields gracefully — counts, never crashes.

Output: table to stdout + adw_data/routing_stats.json.

Usage:
  python3 tools/ledger_stats.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER = REPO_ROOT / "adw_data" / "dispatch_ledger.jsonl"
OUTPUT = REPO_ROOT / "adw_data" / "routing_stats.json"


def _load_ledger(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def run(*, ledger: Path = LEDGER, output: Path = OUTPUT) -> int:
    """Core aggregation. Returns exit code 0."""
    rows = _load_ledger(ledger)
    if not rows:
        print("(empty ledger)")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"routes": [], "rows": 0}))
        return 0

    # Group wait_results by (task_id, dispatch_id)
    wait_results: dict[tuple[str, str], dict] = {}
    for r in rows:
        if r.get("event") != "wait_result":
            continue
        tid = r.get("task_id", "")
        did = r.get("dispatch_id", "")
        if tid and did:
            wait_results[(tid, did)] = r

    # Aggregate dispatches by route
    routes: dict[str, dict] = {}
    for r in rows:
        if r.get("event") != "dispatch":
            continue
        route = r.get("route", "unknown")
        if route not in routes:
            routes[route] = {
                "n_dispatches": 0, "n_completed": 0,
                "wait_rcs": [], "cost_deltas": [],
            }
        rec = routes[route]
        rec["n_dispatches"] += 1
        tid = r.get("task_id", "")
        did = r.get("dispatch_id", "")
        wr = wait_results.get((tid, did))
        if wr and wr.get("rc") == 0:
            rec["n_completed"] += 1
        if wr:
            rec["wait_rcs"].append(wr.get("rc", 0))
        # cost_usd_delta: sum usd_per_m_in + usd_per_m_out if present
        cost = None
        if "usd_per_m_in" in r or "usd_per_m_out" in r:
            cost_in = r.get("usd_per_m_in", 0) or 0
            cost_out = r.get("usd_per_m_out", 0) or 0
            cost = cost_in + cost_out
        elif "cost_usd_delta" in r:
            cost = r.get("cost_usd_delta")
        if cost is not None:
            rec["cost_deltas"].append(cost)

    # Compute per-route stats
    result_routes = []
    print(f"{'ROUTE':25} {'DISP':>5} {'COMP':>5} {'FPR':>7} {'MEAN_RC':>8} {'MEAN_COST':>10}")
    print("-" * 70)
    for route in sorted(routes):
        rec = routes[route]
        n = rec["n_dispatches"]
        cmp = rec["n_completed"]
        fpr = f"{cmp / n:.1%}" if n else "N/A"
        mean_rc = (f"{sum(rec['wait_rcs']) / len(rec['wait_rcs']):.2f}"
                   if rec["wait_rcs"] else "N/A")
        mean_cost = (f"${sum(rec['cost_deltas']) / len(rec['cost_deltas']):.4f}"
                     if rec["cost_deltas"] else "N/A")
        print(f"{route:25} {n:5} {cmp:5} {fpr:>7} {mean_rc:>8} {mean_cost:>10}")
        result_routes.append({
            "route": route,
            "n_dispatches": n,
            "n_completed": cmp,
            "first_pass_rate": fpr,
            "mean_wait_rc": mean_rc,
            "mean_cost_usd_delta": mean_cost,
        })

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({"routes": result_routes, "rows": len(result_routes)}, indent=2))
    return 0


def main() -> int:
    return run()


if __name__ == "__main__":
    sys.exit(main())