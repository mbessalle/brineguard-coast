"""Tests for adws/adw.py — the ADW chain menu launcher.

No live model/API calls: run_route / run_claude are mocked, subprocess is
mocked, and the dry-run / unknown-name paths never touch the backend.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

_adws = Path(__file__).resolve().parent.parent / "adws"
sys.path.insert(0, str(_adws))

import adw  # noqa: E402
import adw_common  # noqa: E402

# The spec's ADW table, as the source of truth for composition. Each value is
# the ordered machine-executed phase list (the "engineer ->" prefix and the
# "[-> builder(fix/revise) ... bounded]" retry annotations are not phases).
EXPECTED = {
    "adw_prompt": ["<agent>"],
    "adw_scout": ["scout"],
    "adw_plan": ["planner"],
    "adw_build": ["builder"],
    "adw_quality": ["code(quality)"],
    "adw_document": ["code(changes)", "documenter"],
    "adw_plan_build": ["planner", "builder", "git(commit)"],
    "adw_build_test": ["builder", "code(test)"],
    "adw_build_review": ["builder", "reviewer"],
    "adw_plan_build_test": ["planner", "builder", "code(test)", "git(commit)"],
    "adw_plan_build_test_quality": ["planner", "builder", "code(verify)", "code(test)", "git(commit)"],
    "adw_simple_sdlc": ["planner", "git(commit_plan)", "builder", "code(test)",
                        "reviewer", "documenter", "git(commit)"],
}

ALL_NAMES = set(EXPECTED)


# ---------------------------------------------------------------------------
# Table completeness (AC1)
# ---------------------------------------------------------------------------

class TestTableCompleteness:
    def test_all_12_chains_in_data(self):
        assert set(adw.CHAINS) == ALL_NAMES

    def test_list_prints_all_12_names(self, capsys):
        adw.print_chain_list()
        out = capsys.readouterr().out
        for name in ALL_NAMES:
            assert name in out

    def test_list_has_three_columns(self, capsys):
        adw.print_chain_list()
        out = capsys.readouterr().out
        assert "ADW" in out
        assert "Chain" in out
        assert "Use when" in out

    def test_list_via_cli_flag(self, capsys):
        assert adw.main(["--list"]) == 0
        out = capsys.readouterr().out
        for name in ALL_NAMES:
            assert name in out


# ---------------------------------------------------------------------------
# Per-chain composition correctness (AC3 / AC6)
# ---------------------------------------------------------------------------

class TestComposition:
    def test_each_chain_matches_spec_table(self):
        for name, expected_phases in EXPECTED.items():
            assert adw.CHAINS[name]["phases"] == expected_phases, name

    def test_chains_are_data_not_functions(self):
        # Execution is composed from the DATA table, not hard-wired per chain.
        for name in ALL_NAMES:
            assert isinstance(adw.CHAINS[name]["phases"], list)
            assert isinstance(adw.CHAINS[name]["use_when"], str)


# ---------------------------------------------------------------------------
# Dry-run: prints ordered phases, makes ZERO model/subprocess calls (AC2)
# ---------------------------------------------------------------------------

class TestDryRun:
    def test_dry_run_makes_no_calls(self, capsys):
        with mock.patch("adw_common.run_route") as m_route, \
             mock.patch("adw_common.run_claude") as m_claude, \
             mock.patch("adw.subprocess.run") as m_subprocess:
            rc = adw.run_chain("adw_simple_sdlc", "x", dry_run=True)
            capsys.readouterr()
        assert rc == 0
        m_route.assert_not_called()
        m_claude.assert_not_called()
        m_subprocess.assert_not_called()

    def test_dry_run_prints_ordered_phases(self, capsys):
        rc = adw.run_chain("adw_plan_build_test", "x", dry_run=True)
        out = capsys.readouterr().out
        assert rc == 0
        for phase in ["planner", "builder", "code(test)", "git(commit)"]:
            assert phase in out

    def test_dry_run_every_chain_no_calls(self, capsys):
        with mock.patch("adw_common.run_route") as m_route, \
             mock.patch("adw_common.run_claude") as m_claude, \
             mock.patch("adw.subprocess.run") as m_subprocess:
            for name in ALL_NAMES:
                assert adw.run_chain(name, "x", dry_run=True) == 0
            capsys.readouterr()
        m_route.assert_not_called()
        m_claude.assert_not_called()
        m_subprocess.assert_not_called()


# ---------------------------------------------------------------------------
# Unknown-name behavior (AC4)
# ---------------------------------------------------------------------------

class TestUnknownName:
    def test_unknown_returns_nonzero_and_lists_chains(self, capsys):
        rc = adw.run_chain("nonexistent", "x", dry_run=True)
        out = capsys.readouterr().out
        assert rc != 0
        assert "adw_scout" in out

    def test_unknown_via_cli(self, capsys):
        rc = adw.main(["run", "nonexistent", "--request", "x"])
        out = capsys.readouterr().out
        assert rc != 0
        assert "adw_plan_build_test" in out


# ---------------------------------------------------------------------------
# Delegation (AC5)
# ---------------------------------------------------------------------------

class TestDelegation:
    def test_plan_build_test_delegates_to_existing_module(self):
        with mock.patch("adw_plan_build_test.run", return_value=7) as m:
            rc = adw.run_chain("adw_plan_build_test", "x", dry_run=False, commit=False)
        assert rc == 7
        m.assert_called_once_with("x", dry_run=False, commit=False)

    def test_simple_sdlc_delegates_to_existing_module(self):
        with mock.patch("adw_simple_sdlc.run", return_value=9) as m:
            rc = adw.run_chain("adw_simple_sdlc", "x", dry_run=False, commit=False)
        assert rc == 9
        m.assert_called_once_with("x", dry_run=False, commit=False)
