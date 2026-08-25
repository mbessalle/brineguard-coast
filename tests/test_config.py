import pytest

from brineguard.config import load_config


def test_first_slice_loads():
    config = load_config("configs/first_slice.yaml")
    assert config["run"]["id"] == "first-slice"
    assert config["dispatch"]["horizon_hours"] == 24
    assert len(config["dispatch"]["demand_m3_h"]) == 24


def test_phase3_loads():
    config = load_config("configs/phase3.yaml")
    assert config["run"]["id"] == "phase3-benchmark"
    assert config["dispatch"]["horizon_hours"] == 48
    assert len(config["dispatch"]["demand_m3_h"]) == 96
    assert config["rolling"] == {"enact_hours": 6, "total_hours": 96}
    assert config["dispatch"]["plants"][0]["local_receptors"] == ["near_north"]


def test_bad_local_receptors_name_raises():
    from brineguard.config import load_config as _load
    _load("configs/first_slice.yaml")  # verify original loads
    import copy, yaml
    with open("configs/first_slice.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["dispatch"]["plants"][0]["local_receptors"] = ["nonexistent"]
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf)
        tmp = tf.name
    try:
        with pytest.raises(ValueError, match="nonexistent"):
            _load(tmp)
    finally:
        os.unlink(tmp)


def test_demand_shorter_than_horizon_raises():
    import copy, yaml
    with open("configs/first_slice.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["dispatch"]["horizon_hours"] = 48  # demand is still 24
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf)
        tmp = tf.name
    try:
        with pytest.raises(ValueError, match=">= horizon_hours"):
            load_config(tmp)
    finally:
        os.unlink(tmp)


def test_horizon_12_raises():
    import copy, yaml
    with open("configs/first_slice.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["dispatch"]["horizon_hours"] = 12
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf)
        tmp = tf.name
    try:
        with pytest.raises(ValueError, match="must be 24 or 48"):
            load_config(tmp)
    finally:
        os.unlink(tmp)


def test_rolling_enact_ge_horizon_raises():
    import copy, yaml
    with open("configs/phase3.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["rolling"]["enact_hours"] = 48  # horizon is 48
    import tempfile, os
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as tf:
        yaml.safe_dump(cfg, tf)
        tmp = tf.name
    try:
        with pytest.raises(ValueError, match="1 <= enact_hours < horizon_hours"):
            load_config(tmp)
    finally:
        os.unlink(tmp)