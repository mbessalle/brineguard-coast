import copy
import numpy as np
from brineguard.config import load_config
from brineguard.domain import generate_domain
from brineguard.transport.solver import advance
from brineguard.transport.validation import validate_pulse


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
