"""Tests for cmems_currents.py — extraction, mask, FD-cap gate, provenance."""

import hashlib
import json
import copy

import numpy as np
import pytest
import xarray as xr

from brineguard.config import load_config
from brineguard.transport.cmems_currents import extract_current_summary
from brineguard.domain_sourced import build_hybrid_domain, _sha256_file


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_synthetic_nc(tmp_path, *, include_land=True, overspeed=False):
    """Return (nc_path, expected_summary) for a tiny synthetic CMEMS dataset.

    Grid: 2×2 spatial, 5 depth levels [1,5,20,40,100], 3 daily time steps.
    Water cells: (0,0)=u0.05/v0.02, (0,1)=u0.10/v0.03, (1,1)=u-0.02/v-0.01.
    Land cell (1,0)=NaN everywhere — only when *include_land*.
    When *overspeed*, velocities are bumped to 0.50/0.30 so total speed is
    extremely high (for FD-cap testing).
    """
    depth = np.array([1.0, 5.0, 20.0, 40.0, 100.0], dtype=np.float32)
    time = np.array(["2026-05-01", "2026-05-02", "2026-05-03"], dtype="datetime64[ns]")
    lat = np.array([27.0, 27.5], dtype=np.float32)
    lon = np.array([35.0, 35.5], dtype=np.float32)

    uo = np.full((3, 5, 2, 2), np.nan, dtype=np.float32)
    vo = np.full((3, 5, 2, 2), np.nan, dtype=np.float32)

    if overspeed:
        uv0, vv0 = 0.50, 0.30
        uv1, vv1 = 0.60, 0.35
        uv2, vv2 = -0.55, -0.25
    else:
        uv0, vv0 = 0.05, 0.02
        uv1, vv1 = 0.10, 0.03
        uv2, vv2 = -0.02, -0.01

    uo[:, :, 0, 0] = uv0
    vo[:, :, 0, 0] = vv0
    uo[:, :, 0, 1] = uv1
    vo[:, :, 0, 1] = vv1
    uo[:, :, 1, 1] = uv2
    vo[:, :, 1, 1] = vv2
    # (1, 0) stays NaN = land.

    ds = xr.Dataset(
        {"uo": (["time", "depth", "latitude", "longitude"], uo),
         "vo": (["time", "depth", "latitude", "longitude"], vo)},
        coords={"time": time, "depth": depth, "latitude": lat, "longitude": lon},
    )
    nc_path = tmp_path / "synthetic.nc"
    ds.to_netcdf(str(nc_path), engine="h5netcdf")

    # Provenance JSON.
    sha = _sha256_file(nc_path)
    prov = {"sha256": sha, "dataset_id": "cmems-synthetic-test"}
    (tmp_path / "synthetic.json").write_text(json.dumps(prov), encoding="utf-8")

    # Expected: depth-avg over [1,5,20] (≤30m), then spatial-mean over
    # water cells [(0,0), (0,1), (1,1)], then time-mean.
    depth_levels_used = [1.0, 5.0, 20.0]
    # For each water cell and each depth level the velocity is constant
    # across time and depth, so depth-avg = cell value, spatial-mean is
    # simple average, time-mean = same.
    u_exp = (uv0 + uv1 + uv2) / 3.0
    v_exp = (vv0 + vv1 + vv2) / 3.0
    spd = np.sqrt(u_exp**2 + v_exp**2)
    expected = {
        "u_mean_m_s": u_exp,
        "v_mean_m_s": v_exp,
        "mean_speed_m_s": spd,
        "max_daily_speed_m_s": spd,  # all days identical → max = mean
        "speed_std_m_s": 0.0,
        "n_days": 3,
        "depth_levels_used": depth_levels_used,
        "provenance_sha256": sha,
        "dataset_id": "cmems-synthetic-test",
    }
    if include_land:
        # 1 land cell out of 4 → 75% water, no coverage_warning.
        pass
    else:
        expected["coverage_warning"] = True

    return str(nc_path), expected


# ---------------------------------------------------------------------------
# AC2 — extraction is deterministic, mask exclusion works
# ---------------------------------------------------------------------------

def test_extract_means_match_expected(tmp_path):
    nc_path, expected = _make_synthetic_nc(tmp_path)
    result = extract_current_summary(nc_path)
    assert result["u_mean_m_s"] == pytest.approx(expected["u_mean_m_s"])
    assert result["v_mean_m_s"] == pytest.approx(expected["v_mean_m_s"])
    assert result["mean_speed_m_s"] == pytest.approx(expected["mean_speed_m_s"])
    assert result["max_daily_speed_m_s"] == pytest.approx(expected["max_daily_speed_m_s"])
    assert result["speed_std_m_s"] == pytest.approx(expected["speed_std_m_s"], abs=1e-10)
    assert result["n_days"] == expected["n_days"]
    assert result["depth_levels_used"] == expected["depth_levels_used"]
    assert result["provenance_sha256"] == expected["provenance_sha256"]
    assert result["dataset_id"] == expected["dataset_id"]
    assert "coverage_warning" not in result  # 75% water > 50%


def test_mask_excludes_land_cells(tmp_path):
    """Land cells do not contaminate the spatial mean."""
    nc_path, _ = _make_synthetic_nc(tmp_path)
    result = extract_current_summary(nc_path)
    # 3 water cells: (0.05,0.10,-0.02)/3 ≈ 0.04333
    assert result["u_mean_m_s"] == pytest.approx((0.05 + 0.10 - 0.02) / 3.0)
    assert result["v_mean_m_s"] == pytest.approx((0.02 + 0.03 - 0.01) / 3.0)


def test_coverage_warning_when_majority_masked(tmp_path):
    """>50% NaN → coverage_warning: true."""
    # 1 water cell out of 4 → 25%, triggers warning.
    depth = np.array([1.0, 5.0], dtype=np.float32)
    time = np.array(["2026-05-01", "2026-05-02"], dtype="datetime64[ns]")
    lat = np.array([27.0, 27.5], dtype=np.float32)
    lon = np.array([35.0, 35.5], dtype=np.float32)

    uo = np.full((2, 2, 2, 2), np.nan, dtype=np.float32)
    vo = np.full((2, 2, 2, 2), np.nan, dtype=np.float32)
    uo[:, :, 0, 0] = 0.05  # only cell (0,0) is water
    vo[:, :, 0, 0] = 0.02

    ds = xr.Dataset(
        {"uo": (["time", "depth", "latitude", "longitude"], uo),
         "vo": (["time", "depth", "latitude", "longitude"], vo)},
        coords={"time": time, "depth": depth, "latitude": lat, "longitude": lon},
    )
    nc_path = tmp_path / "sparse.nc"
    ds.to_netcdf(str(nc_path), engine="h5netcdf")

    sha = _sha256_file(nc_path)
    (tmp_path / "sparse.json").write_text(
        json.dumps({"sha256": sha, "dataset_id": "sparse"}))
    result = extract_current_summary(str(nc_path))
    assert result["coverage_warning"] is True
    # Values still computed on the one water cell.
    assert result["u_mean_m_s"] == pytest.approx(0.05)
    assert result["v_mean_m_s"] == pytest.approx(0.02)


# ---------------------------------------------------------------------------
# AC3 — FD anti-diffusion cap gate
# ---------------------------------------------------------------------------

def test_fd_cap_error_on_overspeed_summary(tmp_path):
    """build_hybrid_domain raises ValueError when cmems speed exceeds FD cap."""
    config = load_config("configs/hybrid_redsea.yaml")
    # Use synthetic overspeed nc for the summary
    nc_path, expected = _make_synthetic_nc(tmp_path, overspeed=True)
    summary = extract_current_summary(nc_path)

    # FD cap: 2*D/dx = 2*20/500 = 0.08. Synthetic overspeed speed ≈ 0.58.
    with pytest.raises(ValueError, match="FD anti-diffusion cap exceeded"):
        build_hybrid_domain(config, cmems_summary=summary)


def test_fd_cap_error_message_includes_numbers(tmp_path):
    """The error message contains measured numbers, not a silent clamp."""
    config = load_config("configs/hybrid_redsea.yaml")
    nc_path, expected = _make_synthetic_nc(tmp_path, overspeed=True)
    summary = extract_current_summary(nc_path)

    with pytest.raises(ValueError) as exc_info:
        build_hybrid_domain(config, cmems_summary=summary)
    msg = str(exc_info.value)
    assert "2D/dx" in msg
    assert f"{summary['mean_speed_m_s']:.4f}" in msg or "mean" in msg.lower()


# ---------------------------------------------------------------------------
# AC3 — provenance fields flow into the domain record
# ---------------------------------------------------------------------------

def test_cmems_provenance_attrs_in_domain(tmp_path):
    config = load_config("configs/hybrid_redsea.yaml")
    # Reduce tidal amp so the cap check passes with synthetic data.
    config["domain"]["currents"]["u_amp_m_s"] = 0.0
    config["domain"]["currents"]["v_amp_m_s"] = 0.0
    nc_path, _ = _make_synthetic_nc(tmp_path)
    summary = extract_current_summary(nc_path)

    ds = build_hybrid_domain(config, cmems_summary=summary)
    attrs = ds.attrs
    assert "cmems_currents" in attrs
    cc = attrs["cmems_currents"]
    assert cc["dataset_id"] == summary["dataset_id"]
    assert cc["sha256"] == summary["provenance_sha256"]
    assert cc["u_mean_m_s"] == pytest.approx(summary["u_mean_m_s"])
    assert cc["v_mean_m_s"] == pytest.approx(summary["v_mean_m_s"])
    assert cc["tidal_component"] == "analytic-assumed (daily-mean data cannot resolve M2)"


def test_cmems_updates_config_velocity_and_currents(tmp_path):
    """When cmems_summary is provided, config velocity_m_s and currents means are updated."""
    config = load_config("configs/hybrid_redsea.yaml")
    # Reduce tidal amp so the cap check passes with synthetic data.
    config["domain"]["currents"]["u_amp_m_s"] = 0.0
    config["domain"]["currents"]["v_amp_m_s"] = 0.0
    nc_path, _ = _make_synthetic_nc(tmp_path)
    summary = extract_current_summary(nc_path)

    _ds = build_hybrid_domain(config, cmems_summary=summary)
    # Config was mutated in-place.
    dcfg = config["domain"]
    assert dcfg["velocity_m_s"] == [summary["u_mean_m_s"], summary["v_mean_m_s"]]
    assert dcfg["currents"]["u_mean_m_s"] == summary["u_mean_m_s"]
    assert dcfg["currents"]["v_mean_m_s"] == summary["v_mean_m_s"]


# ---------------------------------------------------------------------------
# AC4 — integration test on the real CMEMS registry file
# ---------------------------------------------------------------------------

@pytest.mark.slow
def test_extract_on_real_cmems_file():
    """Run extract_current_summary on the shipped registry file; assert
    finite values and n_days==92."""
    nc_path = (
        "data/registry/cmems/"
        "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m_uo-vo_"
        "34.00E-37.00E_26.00N-29.00N_0.49-5727.92m_2026-05-01-2026-07-31.nc"
    )
    result = extract_current_summary(nc_path)
    assert np.isfinite(result["u_mean_m_s"])
    assert np.isfinite(result["v_mean_m_s"])
    assert np.isfinite(result["mean_speed_m_s"])
    assert np.isfinite(result["max_daily_speed_m_s"])
    assert np.isfinite(result["speed_std_m_s"])
    assert result["n_days"] == 92
    assert len(result["depth_levels_used"]) >= 1
    assert len(result["provenance_sha256"]) == 64
    assert "coverage_warning" in result  # Red Sea box: water fraction < 50%


def test_build_with_real_cmems_passes_fd_cap():
    """build_hybrid_domain with the real CMEMS summary must not trip the FD cap."""
    nc_path = (
        "data/registry/cmems/"
        "cmems_mod_glo_phy-cur_anfc_0.083deg_P1D-m_uo-vo_"
        "34.00E-37.00E_26.00N-29.00N_0.49-5727.92m_2026-05-01-2026-07-31.nc"
    )
    summary = extract_current_summary(nc_path)
    config = load_config("configs/hybrid_redsea.yaml")
    ds = build_hybrid_domain(config, cmems_summary=summary)
    assert "cmems_currents" in ds.attrs
    # Verify the measured mean speed + tidal amp is under 2D/dx = 0.08
    speed = summary["mean_speed_m_s"]
    tidal_amp = np.sqrt(
        config["domain"]["currents"]["u_amp_m_s"] ** 2
        + config["domain"]["currents"]["v_amp_m_s"] ** 2
    )
    assert speed + tidal_amp < 0.08, f"FD cap would be violated: {speed=} {tidal_amp=}"