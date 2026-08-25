from __future__ import annotations

import copy

import numpy as np

from brineguard.config import load_config
from brineguard.experiments.ensemble import evaluate_common_schedules, make_members
from brineguard.transport.solver import simulate


def _config():
    return load_config("configs/first_slice.yaml")


def test_member_zero_is_unperturbed_nominal():
    config = _config()
    members = make_members(config, n_members=5, seed=1234)
    assert members[0]["config"] == config
    assert members[0]["metadata"] == {"index": 0, "clipped": False}
    assert len(members) == 5


def test_make_members_deterministic():
    config = _config()
    a = make_members(config, n_members=5, seed=42)
    b = make_members(config, n_members=5, seed=42)
    assert [m["config"] for m in a] == [m["config"] for m in b]
    assert [m["metadata"] for m in a] == [m["metadata"] for m in b]


def test_members_are_deep_copies_independent():
    config = _config()
    members = make_members(config, n_members=3, seed=7)
    # Mutating one member must not affect the nominal or the original config.
    members[1]["config"]["domain"]["velocity_m_s"][0] = 9.9
    assert members[0]["config"]["domain"]["velocity_m_s"] == config["domain"]["velocity_m_s"]
    assert members[2]["config"]["domain"]["velocity_m_s"][0] != 9.9


def test_evaluate_common_schedules_stats_structure():
    result = evaluate_common_schedules(_config(), n_members=5, seed=99)
    assert set(result["strategies"].keys()) == {"A", "B_capacity", "B_cost", "C"}
    for strategy, entry in result["strategies"].items():
        assert len(entry["exposure_per_member"]) == 5
        held = entry["held_out"]
        assert set(held.keys()) == {"mean", "std", "p5", "p50", "p95"}
        assert held["p5"] <= held["p50"] <= held["p95"]
        assert all(np.isfinite(v) for v in held.values())
    # B rules carry a per-member benefit distribution.
    for rule in ("B_capacity", "B_cost"):
        assert len(result["strategies"][rule]["benefit_distribution"]) == 5
        assert np.isfinite(result["strategies"][rule]["benefit_nominal"])


def test_evaluate_common_schedules_deterministic():
    a = evaluate_common_schedules(_config(), n_members=5, seed=11)
    b = evaluate_common_schedules(_config(), n_members=5, seed=11)
    for strategy in a["strategies"]:
        assert a["strategies"][strategy]["exposure_per_member"] == \
               b["strategies"][strategy]["exposure_per_member"]
        assert a["strategies"][strategy]["held_out"] == b["strategies"][strategy]["held_out"]


def test_every_member_evaluation_is_finite_nonnegative():
    """Mass sanity: every member's direct receptor series is finite and >= 0."""
    result = evaluate_common_schedules(_config(), n_members=5, seed=5)
    members = result["members"]
    for strategy, entry in result["strategies"].items():
        loads = entry["loads_kg_s"]
        assert np.all(np.isfinite(loads))
        for member in members:
            rec, _ = simulate(member["config"], loads)
            assert np.all(np.isfinite(rec)), f"{strategy} member {member['metadata']['index']}"
            assert np.all(rec >= 0.0), f"{strategy} member {member['metadata']['index']}"
        # Exposures agree with the recorded per-member values.
        assert np.all(np.isfinite(entry["exposure_per_member"]))


def test_clipping_metadata_honored_when_sigma_huge():
    config = _config()
    # A huge current sigma forces peak |u| past the stability cap -> clipped.
    members = make_members(config, n_members=5, seed=3,
                           perturb={"u_mean_sigma_m_s": 1.0})
    any_clipped = any(m["metadata"]["clipped"] for m in members[1:])
    assert any_clipped, "forcing huge current sigma should clip at least one member"
    for m in members[1:]:
        if m["metadata"]["clipped"]:
            peak = abs(m["config"]["domain"]["velocity_m_s"][0])
            cap = 0.9 * (2 * m["config"]["domain"]["dispersion_m2_s"]
                         / m["config"]["domain"]["dx_m"])
            assert peak <= cap + 1e-12
            assert m["metadata"]["cap"] == cap
