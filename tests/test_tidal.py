import copy

import numpy as np
import pytest

from brineguard.config import load_config
from brineguard.transport.kernels import KERNEL_VERSION, build_kernel, kernel_cache_key, reconstruct
from brineguard.transport.solver import simulate
from brineguard.transport.validation import kernel_agreement, validate_pulse


def _tidal_current_params():
    return {
        "type": "tidal",
        "u_mean_m_s": 0.03,
        "v_mean_m_s": 0.0,
        "u_amp_m_s": 0.04,
        "v_amp_m_s": 0.0,
        "period_h": 12.42,
        "phase_h": 0.0,
        "t0_h": 0.0,
    }


def _steady_current_params(u=0.04, v=0.0):
    return {
        "type": "steady",
        "u_mean_m_s": u,
        "v_mean_m_s": v,
    }


# ---------------------------------------------------------------------------
# (a) steady backward compat
# ---------------------------------------------------------------------------

def test_steady_currents_section_is_backward_compatible():
    """Kernel and solver produce identical results with/without explicit steady currents section."""
    base = load_config("configs/first_slice.yaml")
    with_cur = copy.deepcopy(base)
    with_cur["domain"]["currents"] = _steady_current_params(
        u=base["domain"]["velocity_m_s"][0],
        v=base["domain"]["velocity_m_s"][1],
    )

    kernel_base = build_kernel(base)
    kernel_cur = build_kernel(with_cur)
    assert np.array_equal(kernel_base, kernel_cur)

    loads = np.random.default_rng(42).uniform(0, 0.7, (24, 3))
    direct_base, _ = simulate(base, loads)
    direct_cur, _ = simulate(with_cur, loads)
    assert np.allclose(direct_base, direct_cur, rtol=1e-12)

    assert KERNEL_VERSION == "gaussian-puff-image-v2"


# ---------------------------------------------------------------------------
# (b) analytic displacement integral
# ---------------------------------------------------------------------------

def _tidal_u(t_s, mean, amp, period_s, phase_s):
    omega = 2.0 * np.pi / period_s
    return mean + amp * np.cos(omega * (t_s - phase_s))


def _analytic_displacement(mean, amp, period_s, phase_s, t_r, age):
    omega = 2.0 * np.pi / period_s
    arg0 = omega * (t_r - phase_s)
    arg1 = omega * (t_r + age - phase_s)
    return mean * age + amp / omega * (np.sin(arg1) - np.sin(arg0))


def test_analytic_displacement_matches_quadrature():
    """The exact analytic integral matches high-resolution trapezoidal quadrature."""
    mean, amp = 0.03, 0.04
    period_s = 12.42 * 3600.0
    phase_s = 0.0
    # Several (release, age) pairs
    for t_r_h in (0.0, 3.5, 11.0, 24.0):
        for age_h in (0.5, 2.0, 8.0, 16.0, 30.0):
            t_r = t_r_h * 3600.0
            age = age_h * 3600.0
            analytic = _analytic_displacement(mean, amp, period_s, phase_s, t_r, age)
            # Quadrature with high resolution over the interval
            n_pts = max(int(age / 0.02), 500)
            t_samples = np.linspace(t_r, t_r + age, n_pts)
            u_samples = _tidal_u(t_samples, mean, amp, period_s, phase_s)
            quadrature = float(np.trapezoid(u_samples, t_samples))
            assert abs(analytic - quadrature) < 1e-9, (
                f"t_r={t_r_h}h age={age_h}h: analytic={analytic:.12e} quad={quadrature:.12e}"
            )


# ---------------------------------------------------------------------------
# (c) tidal kernel is NOT lag-stationary
# ---------------------------------------------------------------------------

def test_tidal_kernel_is_not_lag_stationary():
    """Under tidal currents the kernel varies with release time for the same lag."""
    config = load_config("configs/phase3_tidal.yaml")
    kernel = build_kernel(config)
    hours = config["dispatch"]["horizon_hours"]
    found_nonstationary = False
    for lag in range(1, hours - 1):
        reference = kernel[:, :, lag, 0]
        for release in range(1, hours - lag):
            rel_diff = np.abs(kernel[:, :, release + lag, release] - reference)
            max_abs = np.abs(reference).max() or 1.0
            if (rel_diff / max_abs).max() > 1e-9:
                found_nonstationary = True
                break
        if found_nonstationary:
            break
    assert found_nonstationary, "tidal kernel should vary across release times for the same lag"


# ---------------------------------------------------------------------------
# (d) kernel_agreement gate on tidal config
# ---------------------------------------------------------------------------

def test_kernel_agreement_on_tidal_config():
    """Kernel agrees with direct solver on the tidal config within declared gates."""
    config = load_config("configs/phase3_tidal.yaml")
    # Use a 24h-truncated copy for speed
    config["dispatch"]["horizon_hours"] = 24
    loads = np.random.default_rng(7).uniform(0, 0.7, (24, len(config["domain"]["outfalls"])))
    direct, _ = simulate(config, loads)
    kernel = build_kernel(config)
    result = kernel_agreement(config, direct, reconstruct(kernel, loads))
    assert result["kernel_agreement_pass"], result


# ---------------------------------------------------------------------------
# (e) mass conservation on tidal config
# ---------------------------------------------------------------------------

def test_mass_conservation_on_tidal_config():
    """Mass conservation holds on the tidal config."""
    config = load_config("configs/phase3_tidal.yaml")
    result = validate_pulse(config)
    assert result["mass_pass"], result
    assert "analytical_gate" in result
    assert result["analytical_gate"] == "skipped (nonstationary currents)"


# ---------------------------------------------------------------------------
# (f) cache key changes with tidal parameters
# ---------------------------------------------------------------------------

def test_cache_key_changes_with_tidal_params():
    """Cache key changes when u_amp_m_s, phase_h, or t0_h change."""
    config = load_config("configs/phase3_tidal.yaml")
    key = kernel_cache_key(config)

    # Change u_amp_m_s
    amp_changed = copy.deepcopy(config)
    amp_changed["domain"]["currents"]["u_amp_m_s"] = 0.06
    assert kernel_cache_key(amp_changed) != key

    # Change phase_h
    phase_changed = copy.deepcopy(config)
    phase_changed["domain"]["currents"]["phase_h"] = 3.0
    assert kernel_cache_key(phase_changed) != key

    # Change t0_h
    t0_changed = copy.deepcopy(config)
    t0_changed["domain"]["currents"]["t0_h"] = 6.0
    assert kernel_cache_key(t0_changed) != key

    # Verify steady configs without currents still have None for currents in key payload
    steady = load_config("configs/first_slice.yaml")
    steady_key = kernel_cache_key(steady)
    with_cur = copy.deepcopy(steady)
    with_cur["domain"]["currents"] = _steady_current_params()
    with_key = kernel_cache_key(with_cur)
    # With steady currents section, velocity was already in the key via velocity_m_s
    # but the currents object is now non-None. The key should differ because the
    # payload structure changed (currents went from None to a dict).
    assert steady_key != with_key