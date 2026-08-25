"""Phase 5 T2: evidence bundle generator with reproducibility check."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from brineguard.experiments.benchmark import run_benchmark, _json
from brineguard.experiments.ensemble import run_ensemble
from brineguard.experiments.sensitivity import run_sensitivity


def _parse_freeze_configs(freeze_path: Path) -> list[Path]:
    """Parse ``configs/*.yaml`` paths from FREEZE.md bullet lines."""
    text = freeze_path.read_text(encoding="utf-8")
    paths: list[Path] = []
    for line in text.splitlines():
        m = re.search(r'\b(configs/[\w_]+\.yaml)\b', line)
        if m:
            paths.append(Path(m.group(1)))
    return list(dict.fromkeys(paths))  # dedup, preserve order


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _repo_rel(path: Path, root: Path) -> str:
    """POSIX path of ``path`` relative to ``root``, else ``str(path)``."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _git_dirty() -> bool:
    """True if the working tree has uncommitted changes."""
    r = subprocess.run(
        ["git", "diff-index", "--quiet", "HEAD", "--"],
        capture_output=True, check=False,
    )
    return r.returncode != 0


def _git_revision() -> str:
    r = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True, text=True, check=False,
    )
    return r.stdout.strip() or "unknown"


def make_evidence(output_root: str = "evidence",
                 _benchmark_configs: list[str] | None = None,
                 _ensemble_config_path: str | None = None,
                 _ensemble_n_members: int = 20,
                 _sensitivity_config_path: str | None = None,
                 _sensitivity_n_points: int = 8) -> tuple[Path, dict]:
    """Generate the full evidence bundle (BUILD_PLAN Phase 5 gate).

    Returns ``(bundle_dir, manifest)``.  Writes everything under
    ``<output_root>/<UTC-date>/`` plus a top-level
    ``<output_root>/manifest.json``.
    """
    freeze_path = Path("FREEZE.md")
    all_configs = _parse_freeze_configs(freeze_path)
    if _benchmark_configs is not None:
        existing = [Path(c) for c in _benchmark_configs]
        pending: list[str] = []
    else:
        existing = [c for c in all_configs if c.exists()]
        pending = [str(c) for c in all_configs if not c.exists()]

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bundle_dir = Path(output_root) / date_str
    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)
    bundle_dir.mkdir(parents=True)

    # --- benchmark (frozen configs that exist) ---
    benchmark_dir = None
    if existing:
        benchmark_dir = run_benchmark(
            config_paths=[str(c) for c in existing],
            run_id="benchmark",
            output_root=str(bundle_dir),
        )

    # --- ensemble (phase3_tidal, 20 members, seed 20260825) ---
    ens_path = Path(_ensemble_config_path) if _ensemble_config_path else Path("configs/phase3_tidal.yaml")
    ensemble_dir = None
    if ens_path.exists():
        ensemble_dir = run_ensemble(
            config_path=str(ens_path),
            run_id="ensemble",
            n_members=_ensemble_n_members,
            seed=20260825,
            output_root=str(bundle_dir),
        )

    # --- sensitivity (phase3) ---
    sens_path = Path(_sensitivity_config_path) if _sensitivity_config_path else Path("configs/phase3.yaml")
    sensitivity_dir = None
    if sens_path.exists():
        sensitivity_dir = run_sensitivity(
            config_path=str(sens_path),
            run_id="sensitivity",
            n_points=_sensitivity_n_points,
            output_root=str(bundle_dir),
        )

    # --- top-level manifest ---
    _root = Path.cwd()
    config_sha256s = {
        _repo_rel(c, _root): _file_sha256(c) for c in existing
    }
    artifact_sha256s: dict[str, str] = {}
    for subdir in (benchmark_dir, ensemble_dir, sensitivity_dir):
        if subdir is None or not subdir.is_dir():
            continue
        for fpath in sorted(subdir.rglob("*")):
            if fpath.is_file() and fpath.suffix in (".json", ".csv", ".png"):
                rel = str(fpath.relative_to(bundle_dir))
                artifact_sha256s[rel] = _file_sha256(fpath)

    import numpy as _np
    try:
        import pyomo as _pyomo
        pyomo_ver = _pyomo.__version__
    except Exception:
        pyomo_ver = "unknown"
    try:
        import scipy as _scipy
        scipy_ver = _scipy.__version__
    except Exception:
        scipy_ver = "unknown"

    benchmark_configs_rel = [_repo_rel(c, _root) for c in existing]
    artifact_paths_repo = {
        _repo_rel(bundle_dir / rel, _root): sha
        for rel, sha in artifact_sha256s.items()
    }

    _bundle_cmd = ".venv/bin/python -m brineguard make-evidence"
    _bench_cmd = None
    if existing:
        _bench_cmd = (".venv/bin/python -m brineguard run-benchmark "
                      + " ".join(f"-c {_repo_rel(c, _root)}" for c in existing)
                      + f" --run-id benchmark --output-root {bundle_dir}")
    _ens_cmd = None
    if ensemble_dir:
        _ens_cmd = (".venv/bin/python -m brineguard run-ensemble "
                    f"-c {_repo_rel(ens_path, _root)} --members {_ensemble_n_members} "
                    f"--seed 20260825 --run-id ensemble --output-root {bundle_dir}")
    _sens_cmd = None
    if sensitivity_dir:
        _sens_cmd = (".venv/bin/python -m brineguard run-sensitivity "
                     f"-c {_repo_rel(sens_path, _root)} --n-points {_sensitivity_n_points} "
                     f"--run-id sensitivity --output-root {bundle_dir}")

    manifest: dict = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_revision": _git_revision(),
        "dirty_tree": _git_dirty(),
        "config_sha256s": config_sha256s,
        "artifact_sha256s": artifact_sha256s,
        "artifact_paths_repo": artifact_paths_repo,
        "commands": {
            "bundle": _bundle_cmd,
            "benchmark": _bench_cmd,
            "ensemble": _ens_cmd,
            "sensitivity": _sens_cmd,
        },
        "tool_versions": {
            "python": sys.version.split()[0],
            "numpy": _np.__version__,
            "pyomo": pyomo_ver,
            "scipy": scipy_ver,
        },
        "pending_configs": pending,
        "benchmark_configs": benchmark_configs_rel,
        "ensemble_config_path": _repo_rel(ens_path, _root) if ensemble_dir else None,
        "ensemble_n_members": _ensemble_n_members,
        "sensitivity_config_path": _repo_rel(sens_path, _root) if sensitivity_dir else None,
        "sensitivity_n_points": _sensitivity_n_points,
    }
    _json(Path(output_root) / "manifest.json", manifest)
    return bundle_dir, manifest


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def verify_evidence(bundle_dir: str | Path) -> bool:
    """Re-run evidence generation and compare headline metrics.

    Every coordination_benefit, exposure percentile, and pareto point must
    match within rtol 1e-9.  Returns True if all pass; prints a table and
    exits nonzero (via ``sys.exit(1)``) on any mismatch.
    """
    bundle_dir = Path(bundle_dir)
    output_root = bundle_dir.parent
    orig_manifest = _load_json(output_root / "manifest.json")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_root = Path(tmp)
        new_bundle_dir, _new_manifest = make_evidence(
            output_root=str(tmp_root),
            _benchmark_configs=orig_manifest.get("benchmark_configs") or None,
            _ensemble_config_path=orig_manifest.get("ensemble_config_path"),
            _ensemble_n_members=orig_manifest.get("ensemble_n_members", 20),
            _sensitivity_config_path=orig_manifest.get("sensitivity_config_path"),
            _sensitivity_n_points=orig_manifest.get("sensitivity_n_points", 8),
        )

        results: list[dict] = []

        # --- benchmark: coordination_benefit ---
        orig_bench = bundle_dir / "benchmark" / "comparison.json"
        new_bench = new_bundle_dir / "benchmark" / "comparison.json"
        if orig_bench.exists() and new_bench.exists():
            orig_d = _load_json(orig_bench)
            new_d = _load_json(new_bench)
            for cell_key in sorted(orig_d["cells"]):
                ostrat = orig_d["cells"][cell_key].get("strategies", {})
                nstrat = new_d["cells"][cell_key].get("strategies", {})
                for skey in sorted(ostrat):
                    o_cb = ostrat[skey].get("coordination_benefit")
                    n_cb = nstrat.get(skey, {}).get("coordination_benefit")
                    if o_cb is not None and n_cb is not None:
                        match = abs(o_cb - n_cb) <= 1e-9 * max(abs(o_cb), 1.0)
                    elif o_cb is None and n_cb is None:
                        match = True
                    else:
                        match = False
                    results.append({
                        "source": "benchmark",
                        "cell": cell_key,
                        "strategy": skey,
                        "metric": "coordination_benefit",
                        "original": o_cb,
                        "new": n_cb,
                        "match": match,
                    })

        # --- ensemble: exposure percentiles (held_out p5/p50/p95) ---
        orig_ens = bundle_dir / "ensemble" / "ensemble.json"
        new_ens = new_bundle_dir / "ensemble" / "ensemble.json"
        if orig_ens.exists() and new_ens.exists():
            orig_d = _load_json(orig_ens)
            new_d = _load_json(new_ens)
            for strategy in sorted(orig_d["strategies"]):
                oho = orig_d["strategies"][strategy]["held_out"]
                nho = new_d["strategies"][strategy]["held_out"]
                for pkey in ("p5", "p50", "p95"):
                    o_val = oho[pkey]
                    n_val = nho[pkey]
                    match = abs(o_val - n_val) <= 1e-9 * max(abs(o_val), 1.0)
                    results.append({
                        "source": "ensemble",
                        "strategy": strategy,
                        "metric": f"held_out.{pkey}",
                        "original": o_val,
                        "new": n_val,
                        "match": match,
                    })

        # --- sensitivity: pareto points ---
        orig_sens = bundle_dir / "sensitivity" / "sensitivity.json"
        new_sens = new_bundle_dir / "sensitivity" / "sensitivity.json"
        if orig_sens.exists() and new_sens.exists():
            orig_d = _load_json(orig_sens)
            new_d = _load_json(new_sens)
            opf = orig_d.get("pareto_frontier", [])
            npf = new_d.get("pareto_frontier", [])
            for i, (op, np_) in enumerate(zip(opf, npf)):
                for field in ("energy_cost", "exposure_sum"):
                    o_val = op.get(field)
                    n_val = np_.get(field)
                    if o_val is None and n_val is None:
                        match = True
                    elif o_val is not None and n_val is not None:
                        match = abs(o_val - n_val) <= 1e-9 * max(abs(o_val), 1.0)
                    else:
                        match = False
                    results.append({
                        "source": "sensitivity",
                        "pareto_point": i,
                        "metric": field,
                        "original": o_val,
                        "new": n_val,
                        "match": match,
                    })

        # Print table.
        all_pass = True
        header = f"{'Source':<14} {'Detail':<28} {'Metric':<24} {'Match':<6}"
        sep = "-" * len(header)
        print(sep)
        print(header)
        print(sep)
        for r in results:
            detail = r.get("cell") or r.get("strategy") or f"point_{r.get('pareto_point','')}"
            match_str = "PASS" if r["match"] else "FAIL"
            if not r["match"]:
                all_pass = False
            print(f"{r['source']:<14} {detail:<28} {r['metric']:<24} {match_str:<6}")
        print(sep)
        print(f"{'OVERALL':<14} {'':<28} {'':<24} {'PASS' if all_pass else 'FAIL':<6}")
        print(sep)

        if not all_pass:
            print("\nFAILED: some metrics do not match within rtol 1e-9.")
            sys.exit(1)

    return True