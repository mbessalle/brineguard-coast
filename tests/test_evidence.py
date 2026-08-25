"""Phase 5 T2: evidence bundle tests (mini-bundle with first_slice.yaml)."""
from __future__ import annotations

import json
from pathlib import Path

from brineguard.experiments.evidence import make_evidence, verify_evidence


def _manifest_keys_ok(m: dict) -> bool:
    required = {"created_utc", "git_revision", "dirty_tree",
                "config_sha256s", "artifact_sha256s", "tool_versions"}
    return required.issubset(m.keys())


def test_make_evidence_mini_bundle(tmp_path, monkeypatch):
    """Mini evidence bundle: first_slice for all three stages, tiny settings."""
    output_root = tmp_path / "evidence"

    bundle_dir, manifest = make_evidence(
        output_root=str(output_root),
        _benchmark_configs=["configs/first_slice.yaml"],
        _ensemble_config_path="configs/first_slice.yaml",
        _ensemble_n_members=3,
        _sensitivity_config_path="configs/first_slice.yaml",
        _sensitivity_n_points=3,
    )

    # Top-level manifest exists and has required keys.
    top_manifest_path = output_root / "manifest.json"
    assert top_manifest_path.exists()
    tm = json.loads(top_manifest_path.read_text())
    assert _manifest_keys_ok(tm), f"Missing keys in top manifest: {set(tm.keys())}"
    assert isinstance(tm["config_sha256s"], dict)
    assert len(tm["config_sha256s"]) >= 1
    assert isinstance(tm["artifact_sha256s"], dict)
    assert len(tm["artifact_sha256s"]) >= 1
    assert set(tm["tool_versions"].keys()) == {"python", "numpy", "pyomo", "scipy"}
    # Every sha256 is a 64-char hex string.
    for v in tm["config_sha256s"].values():
        assert len(v) == 64 and all(c in "0123456789abcdef" for c in v)
    for v in tm["artifact_sha256s"].values():
        assert len(v) == 64 and all(c in "0123456789abcdef" for c in v)

    # Bundle subdirectories exist.
    assert (bundle_dir / "benchmark" / "comparison.json").exists()
    assert (bundle_dir / "ensemble" / "ensemble.json").exists()
    assert (bundle_dir / "sensitivity" / "sensitivity.json").exists()

    # Benchmark has strategies and coordination_benefits.
    bench = json.loads((bundle_dir / "benchmark" / "comparison.json").read_text())
    assert "first_slice/flex4" in bench["cells"]
    strat = bench["cells"]["first_slice/flex4"]["strategies"]
    assert "C_matched_capacity" in strat
    assert "coordination_benefit" in strat["C_matched_capacity"]

    # Ensemble has 3 members.
    ens = json.loads((bundle_dir / "ensemble" / "ensemble.json").read_text())
    assert ens["n_members"] == 3
    assert set(ens["strategies"].keys()) == {"A", "B_capacity", "B_cost", "C"}

    # Sensitivity has 3 pareto points.
    sens = json.loads((bundle_dir / "sensitivity" / "sensitivity.json").read_text())
    assert len(sens["pareto_frontier"]) == 3


def test_verify_evidence_passes_on_mini_bundle(tmp_path):
    """verify_evidence returns True on a freshly built mini-bundle."""
    output_root = tmp_path / "evidence"

    bundle_dir, manifest = make_evidence(
        output_root=str(output_root),
        _benchmark_configs=["configs/first_slice.yaml"],
        _ensemble_config_path="configs/first_slice.yaml",
        _ensemble_n_members=3,
        _sensitivity_config_path="configs/first_slice.yaml",
        _sensitivity_n_points=3,
    )

    # Should pass (prints table, returns True, no exit).
    result = verify_evidence(bundle_dir)
    assert result is True


def test_verify_evidence_fails_on_tampered_metric(tmp_path):
    """Tampering one coordination_benefit makes verify fail (sys.exit(1))."""
    output_root = tmp_path / "evidence"
    import sys
    import pytest

    bundle_dir, manifest = make_evidence(
        output_root=str(output_root),
        _benchmark_configs=["configs/first_slice.yaml"],
        _ensemble_config_path="configs/first_slice.yaml",
        _ensemble_n_members=3,
        _sensitivity_config_path="configs/first_slice.yaml",
        _sensitivity_n_points=3,
    )

    # Tamper: bump a coordination_benefit in benchmark/comparison.json.
    bench_path = bundle_dir / "benchmark" / "comparison.json"
    bench = json.loads(bench_path.read_text())
    cb = bench["cells"]["first_slice/flex4"]["strategies"]["C_matched_capacity"]
    cb["coordination_benefit"] = cb["coordination_benefit"] + 0.1 if cb["coordination_benefit"] is not None else 0.5
    bench_path.write_text(json.dumps(bench, indent=2) + "\n", encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        verify_evidence(bundle_dir)
    assert exc.value.code == 1

def test_manifest_enrichment_shape(tmp_path):
    """Enriched manifest: commands, scipy version, repo-relative paths."""
    output_root = tmp_path / "evidence"
    make_evidence(
        output_root=str(output_root),
        _benchmark_configs=["configs/first_slice.yaml"],
        _ensemble_config_path="configs/first_slice.yaml",
        _ensemble_n_members=3,
        _sensitivity_config_path="configs/first_slice.yaml",
        _sensitivity_n_points=3,
    )

    tm = json.loads((output_root / "manifest.json").read_text())

    # scipy added to tool_versions.
    assert tm["tool_versions"]["scipy"]

    # Commands recorded for every section that ran.
    assert set(tm["commands"].keys()) == {"bundle", "benchmark", "ensemble", "sensitivity"}
    assert tm["commands"]["bundle"] == ".venv/bin/python -m brineguard make-evidence"
    assert tm["commands"]["benchmark"] is not None
    assert tm["commands"]["ensemble"] is not None
    assert tm["commands"]["sensitivity"] is not None

    # Config paths stored repo-relative (never absolute).
    assert tm["benchmark_configs"] == ["configs/first_slice.yaml"]
    assert tm["ensemble_config_path"] == "configs/first_slice.yaml"
    assert tm["sensitivity_config_path"] == "configs/first_slice.yaml"
    assert set(tm["config_sha256s"].keys()) == {"configs/first_slice.yaml"}

    # Repo-relative artifact map carries the same sha256s as artifact_sha256s.
    assert sorted(tm["artifact_paths_repo"].values()) == sorted(tm["artifact_sha256s"].values())
