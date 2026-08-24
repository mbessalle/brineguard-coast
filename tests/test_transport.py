import numpy as np
from brineguard.config import load_config
from brineguard.domain import generate_domain
from brineguard.transport.solver import advance
from brineguard.transport.validation import (
    validate_boundaries, validate_linearity, validate_pulse, validate_refinement)


def test_conservative_pulse_mass_and_analytical_transport():
    config = load_config("configs/first_slice.yaml")
    result = validate_pulse(config)
    assert result["mass_pass"], result
    assert result["analytical_pass"], result


def test_one_step_mass_conservation():
    config = load_config("configs/first_slice.yaml")
    cfg = config["domain"]
    wet = generate_domain(config).wet.values
    rng = np.random.default_rng(7)
    initial = np.where(wet, rng.random(wet.shape), 0.0)
    final = advance(initial, wet, dx=cfg["dx_m"], dy=cfg["dy_m"], depth=cfg["depth_m"],
                    u=cfg["velocity_m_s"][0], v=0, dispersion=cfg["dispersion_m2_s"], dt=cfg["transport_dt_s"])
    assert np.isclose(final.sum(), initial.sum(), rtol=1e-12)


def test_zero_source_superposition_and_scaling():
    config = load_config("configs/first_slice.yaml")
    result = validate_linearity(config)
    assert result["linearity_pass"], result
    assert result["zero_source_max_anomaly_kg_m3"] == 0.0


def test_reversing_currents_conserve_mass_without_negatives():
    config = load_config("configs/first_slice.yaml")
    result = validate_boundaries(config)
    assert result["boundary_pass"], result


def test_grid_and_timestep_refinement_within_declared_tolerance():
    config = load_config("configs/first_slice.yaml")
    result = validate_refinement(config)
    assert result["refinement_pass"], result
