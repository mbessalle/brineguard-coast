"""Tests for domain_sourced — hybrid GEBCO domain + Phase 4 gate checks."""

import copy
import json
import shutil

import numpy as np
import pytest

from brineguard.config import load_config
from brineguard.domain_sourced import (
    HYBRID_LABEL,
    _read_registry_sha,
    _registry_json_path,
    _sha256_file,
    build_hybrid_domain,
    checks,
    get_domain,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_HYBRID_CONFIG = "configs/hybrid_redsea.yaml"


# ---------------------------------------------------------------------------
# 1 — checks pass on shipped registry data
# ---------------------------------------------------------------------------

def test_checks_pass_on_shipped_registry_data():
    config = load_config(_HYBRID_CONFIG)
    result = checks(config)
    assert result["provenance_pass"], result["details"]["provenance"]
    assert result["resolution_pass"], result["details"]["resolution"]
    assert result["geometry_pass"], result["details"]["geometry"]


# ---------------------------------------------------------------------------
# 2 — sha mismatch fails provenance
# ---------------------------------------------------------------------------

def test_sha_mismatch_fails_provenance(tmp_path):
    """Tamper the netCDF (one byte flip) so registry sha no longer matches."""
    config = load_config(_HYBRID_CONFIG)
    gebco_path = config["domain"]["gebco_path"]

    # Copy netCDF *and* its registry JSON to tmp, then flip a byte.
    nc_src = gebco_path
    nc_dst = tmp_path / "tampered.nc"
    shutil.copy2(nc_src, nc_dst)
    prov_dst = tmp_path / "tampered.json"
    shutil.copy2(_registry_json_path(nc_src), prov_dst)

    data = bytearray(nc_dst.read_bytes())
    data[1024] ^= 0x01  # flip one bit well past the header
    nc_dst.write_bytes(data)

    config["domain"]["gebco_path"] = str(nc_dst)
    result = checks(config)
    assert result["provenance_pass"] is False, "sha mismatch should fail provenance"
    assert "mismatch" in result["details"]["provenance"].lower()


# ---------------------------------------------------------------------------
# 3 — build produces ≥ 20×20 mixed grid with outfalls/receptors wet
# ---------------------------------------------------------------------------

def test_build_produces_mixed_grid_outfalls_receptors_wet():
    config = load_config(_HYBRID_CONFIG)
    ds = build_hybrid_domain(config)
    wet = ds["wet"].values
    ny, nx = wet.shape
    assert ny >= 20 and nx >= 20, f"grid {ny}×{nx} too small"
    assert wet.any() and (~wet).any(), "need both wet and dry cells"

    outfalls = config["domain"]["outfalls"]
    receptors = config["domain"]["receptors"]
    for item in outfalls + receptors:
        assert wet[item["row"], item["col"]], f"{item['name']} at ({item['row']},{item['col']}) is dry"


# ---------------------------------------------------------------------------
# 4 — attrs carry hybrid label and provenance sha
# ---------------------------------------------------------------------------

def test_hybrid_label_and_sha_in_attrs():
    config = load_config(_HYBRID_CONFIG)
    ds = build_hybrid_domain(config)
    attrs = ds.attrs
    assert attrs["label"] == HYBRID_LABEL
    assert attrs["source"] == "gebco"
    assert "gebco_sha256" in attrs, "missing gebco_sha256 in attrs"

    # sha256 must match the actual registry value.
    recorded = _read_registry_sha(config["domain"]["gebco_path"])
    assert recorded is not None
    assert attrs["gebco_sha256"] == recorded


# ---------------------------------------------------------------------------
# 5 — kernel builds on the hybrid domain (monkeypatch-free integration)
#
# build_kernel hard-imports brineguard.domain.generate_domain — we swap it
# for domain_sourced.get_domain at the module level via pytest's monkeypatch
# fixture. This is the mechanism described in BUILD_PLAN Phase 4 as "patch
# generate_domain usage"; no source files are touched.
# ---------------------------------------------------------------------------

def test_kernel_builds_on_hybrid_domain(monkeypatch):
    from brineguard.transport import kernels
    from brineguard.domain_sourced import get_domain

    monkeypatch.setattr(kernels, "generate_domain", get_domain)
    config = load_config(_HYBRID_CONFIG)
    # Truncate horizon for speed — same pattern as test_tidal.py.
    truncated = copy.deepcopy(config)
    truncated["dispatch"]["horizon_hours"] = 24

    kernel = kernels.build_kernel(truncated)
    n_rec = len(config["domain"]["receptors"])
    n_src = len(config["domain"]["outfalls"])
    hours = 24
    assert kernel.shape == (n_rec, n_src, hours, hours)
    assert np.isfinite(kernel).all(), "kernel contains NaN/Inf"
    assert (kernel >= 0).all(), "kernel entries should be nonnegative"


# ---------------------------------------------------------------------------
# extra — get_domain dispatches correctly
# ---------------------------------------------------------------------------

def test_get_domain_dispatches_hybrid_vs_synthetic():
    hybrid_config = load_config(_HYBRID_CONFIG)
    ds = get_domain(hybrid_config)
    assert "HYBRID" in ds.attrs.get("label", "")

    synthetic = copy.deepcopy(hybrid_config)
    synthetic["domain"].pop("source", None)
    synthetic["domain"].pop("gebco_path", None)
    synthetic["domain"].pop("bbox", None)
    ds_syn = get_domain(synthetic)
    assert "provenance" in ds_syn.attrs
    assert "deterministic synthetic" in ds_syn.attrs["provenance"]


# ---------------------------------------------------------------------------
# extra — allow_hybrid_fallback suppresses the raise on failed check
# ---------------------------------------------------------------------------

def test_allow_hybrid_fallback_proceeds_despite_sha_mismatch(tmp_path):
    config = load_config(_HYBRID_CONFIG)
    nc_src = config["domain"]["gebco_path"]
    nc_dst = tmp_path / "tampered.nc"
    shutil.copy2(nc_src, nc_dst)
    prov_dst = tmp_path / "tampered.json"
    shutil.copy2(_registry_json_path(nc_src), prov_dst)
    data = bytearray(nc_dst.read_bytes())
    data[2048] ^= 0x01
    nc_dst.write_bytes(data)

    config["domain"]["gebco_path"] = str(nc_dst)
    config["domain"]["allow_hybrid_fallback"] = True

    ds = build_hybrid_domain(config)
    assert "checks_failed" in ds.attrs
    assert "provenance_pass" in ds.attrs["checks_failed"]


# ---------------------------------------------------------------------------
# extra — resolution check
# ---------------------------------------------------------------------------

def test_resolution_check_native_cell_size():
    config = load_config(_HYBRID_CONFIG)
    result = checks(config)
    assert result["resolution_pass"]
    # native ~464 m ≤ 1000 m
    assert "464" in result["details"]["resolution"] or "463" in result["details"]["resolution"]


# ---------------------------------------------------------------------------
# extra — geometry detail: coastline fraction ≥ 0.8
# ---------------------------------------------------------------------------

def test_geometry_coastline_fraction():
    config = load_config(_HYBRID_CONFIG)
    result = checks(config)
    geom = result["details"]["geometry"]
    assert geom["coastline_rows_fraction"] >= 0.8
    assert geom["coastline_pass"]


# ---------------------------------------------------------------------------
# extra — uniform depth in dataset matches contract
# ---------------------------------------------------------------------------

def test_uniform_depth_and_true_median_in_attrs():
    config = load_config(_HYBRID_CONFIG)
    ds = build_hybrid_domain(config)
    assert "depth_true_median_m" in ds.attrs
    assert "depth_uniform_m" in ds.attrs
    true_med = ds.attrs["depth_true_median_m"]
    uniform = ds.attrs["depth_uniform_m"]
    assert 5.0 <= uniform <= 30.0
    # true median for the deep Red Sea box should be > 30
    assert true_med > 30.0
    # dataset depth_m matches the uniform scalar on wet cells
    wet = ds["wet"].values
    d = ds["depth_m"].values
    assert np.allclose(d[wet], uniform), "depth_m should be the uniform scalar on wet cells"
    assert np.all(np.isnan(d[~wet])), "depth_m should be NaN on dry cells"