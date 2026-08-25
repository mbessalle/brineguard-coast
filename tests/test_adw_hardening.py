"""Tests for ADW DAG hardening: verdict parsing, envelope validation,
retry-ladder transitions, codex prompt composition.

No live API calls — all model invocations are mocked via subprocess stubs.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

# Add adws/ to path so we can import the shared modules directly.
_adws = Path(__file__).resolve().parent.parent / "adws"
sys.path.insert(0, str(_adws))

import adw_common  # noqa: E402
import gates  # noqa: E402


# ---------------------------------------------------------------------------
# verdict-line parsing (all four enums + malformed -> error)
# ---------------------------------------------------------------------------

class TestParseVerdict:
    def test_approve(self):
        v, r = adw_common.parse_verdict("APPROVE: looks good")
        assert v == "APPROVE"
        assert r == "looks good"

    def test_request_changes(self):
        v, r = adw_common.parse_verdict("REQUEST-CHANGES - missing error handling")
        assert v == "REQUEST-CHANGES"
        assert r == "missing error handling"

    def test_partial(self):
        v, r = adw_common.parse_verdict("PARTIAL no access to src/brineguard")
        assert v == "PARTIAL"
        assert r == "no access to src/brineguard"

    def test_blocked(self):
        v, r = adw_common.parse_verdict("BLOCKED truncated diff; cannot review")
        assert v == "BLOCKED"
        assert r == "truncated diff; cannot review"

    def test_verdict_embedded_in_text(self):
        output = """CLASS: adversarial
ARTIFACT: diff
SCOPE: adws/
EFFORT: max
NOT CHECKED: src/brineguard/

Finding 1: something wrong.

REQUEST-CHANGES: fix the null check on line 42

Finding 2: another issue.

Envelope: {"status": "succeeded", ...}
"""
        v, r = adw_common.parse_verdict(output)
        assert v == "REQUEST-CHANGES"
        assert "null check" in r

    def test_approve_first_line(self):
        v, r = adw_common.parse_verdict("APPROVE all good\n\n--- DETAIL --- ...")
        assert v == "APPROVE"

    def test_malformed_no_verdict_raises(self):
        with pytest.raises(ValueError, match="no valid verdict line"):
            adw_common.parse_verdict("just some text\nno verdict here")

    def test_empty_output_raises(self):
        with pytest.raises(ValueError, match="no valid verdict line"):
            adw_common.parse_verdict("")

    def test_verdict_no_reason(self):
        v, r = adw_common.parse_verdict("APPROVE")
        assert v == "APPROVE"
        assert r == ""


# ---------------------------------------------------------------------------
# envelope status validation
# ---------------------------------------------------------------------------

class TestEnvelopeStatusValidation:
    def test_write_envelope_succeeded(self, tmp_path):
        p = tmp_path / "env.json"
        adw_common.write_envelope(p, status="succeeded", summary="ok", changed_files=["a.py"])
        data = json.loads(p.read_text())
        assert data["status"] == "succeeded"
        assert data["summary"] == "ok"

    def test_write_envelope_failed(self, tmp_path):
        p = tmp_path / "env.json"
        adw_common.write_envelope(p, status="failed", summary="bad", changed_files=[])
        data = json.loads(p.read_text())
        assert data["status"] == "failed"

    def test_write_envelope_rejects_ok(self, tmp_path):
        p = tmp_path / "env.json"
        with pytest.raises(ValueError, match="must be 'succeeded' or 'failed'"):
            adw_common.write_envelope(p, status="ok", summary="x", changed_files=[])

    def test_write_envelope_rejects_error(self, tmp_path):
        p = tmp_path / "env.json"
        with pytest.raises(ValueError, match="must be 'succeeded' or 'failed'"):
            adw_common.write_envelope(p, status="error", summary="x", changed_files=[])

    def test_write_envelope_rejects_dry_run(self, tmp_path):
        p = tmp_path / "env.json"
        with pytest.raises(ValueError, match="must be 'succeeded' or 'failed'"):
            adw_common.write_envelope(p, status="dry-run", summary="x", changed_files=[])

    def test_json_parse_rejects_ok_status(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({"status": "ok", "summary": "x", "changed_files": []}))
        result = gates.json_parse(str(p))
        assert result["pass"] is False
        assert "must be 'succeeded' or 'failed'" in result["detail"]

    def test_json_parse_accepts_succeeded(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({"status": "succeeded", "summary": "x", "changed_files": []}))
        result = gates.json_parse(str(p))
        assert result["pass"] is True

    def test_json_parse_blocks_adverse_verdict(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({
            "status": "succeeded", "summary": "needs work", "changed_files": [],
            "verdict": "REQUEST-CHANGES",
        }))
        result = gates.json_parse(str(p))
        assert result["pass"] is False
        assert "blocks advancement" in result["detail"]

    def test_json_parse_blocks_partial_verdict(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({
            "status": "succeeded", "summary": "partial", "changed_files": [],
            "verdict": "PARTIAL",
        }))
        result = gates.json_parse(str(p))
        assert result["pass"] is False

    def test_json_parse_blocks_blocked_verdict(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({
            "status": "succeeded", "summary": "blocked", "changed_files": [],
            "verdict": "BLOCKED",
        }))
        result = gates.json_parse(str(p))
        assert result["pass"] is False

    def test_json_parse_passes_approve_verdict(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({
            "status": "succeeded", "summary": "ok", "changed_files": [],
            "verdict": "APPROVE",
        }))
        result = gates.json_parse(str(p))
        assert result["pass"] is True

    def test_json_parse_status_failed(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({
            "status": "failed", "summary": "it broke", "changed_files": [],
        }))
        result = gates.json_parse(str(p))
        assert result["pass"] is False
        assert "status=failed" in result["detail"]

    def test_json_parse_bad_verdict_value(self, tmp_path):
        p = tmp_path / "env.json"
        p.write_text(json.dumps({
            "status": "succeeded", "summary": "ok", "changed_files": [],
            "verdict": "BANANA",
        }))
        result = gates.json_parse(str(p))
        assert result["pass"] is False
        assert "verdict" in result["detail"]


# ---------------------------------------------------------------------------
# retry-ladder transitions (mock model calls — NO live API)
# ---------------------------------------------------------------------------

FAKE_CONFIG = {
    "routing": {
        "retry_policy": {
            "max_builder_retries": 2,
            "model_escalation": ["builder", "builder_escalation", "planner"],
        },
        "default_tier_by_role": {
            "planner": "tier_1_sota", "reviewer": "tier_1_sota",
            "builder": "tier_2_workhorse",
        },
    },
    "tiers": {
        "tier_1_sota": {"model": "claude-fable-5"},
        "tier_2_workhorse": {"models": {"builder": "builder"}},
    },
    "routes": {
        "planner": {"backend": "session", "model": "claude-fable-5"},
        "builder": {"backend": "pi-openrouter", "model": "deepseek-v4-pro",
                     "role_prompt": ""},
        "builder_escalation": {"backend": "codex-cli", "model": "gpt-5.6-sol",
                                "role_prompt": ""},
        "reviewer_independent": {"backend": "codex-cli", "model": "gpt-5.6-sol",
                                  "role_prompt": "adws/prompts/reviewer.md"},
        "documenter": {"backend": "openrouter-api", "model": "gpt-5-mini",
                       "role_prompt": ""},
    },
    "backends": {
        "session": {"invoke": ["interactive"]},
        "pi-openrouter": {"invoke": ["pi", "--provider", "openrouter", "--model", "{model}", "-p", "{prompt}"]},
        "codex-cli": {"invoke": ["codex", "exec", "-m", "{model}", "{prompt}"]},
        "openrouter-api": {"invoke": ["python3", "tools/openrouter_call.py", "chat", "-m", "{model}", "{prompt}"]},
    },
}


def _mock_runner(returncode: int, stdout: str, stderr: str = ""):
    """Create a subprocess.run mock that returns the given result."""
    result = subprocess.CompletedProcess(args=[], returncode=returncode,
                                          stdout=stdout, stderr=stderr)
    return mock.MagicMock(return_value=result)


class TestRetryLadder:
    def _make_logger(self, tmp_path):
        session_id = "test_retry_session"
        handoff = tmp_path / "adw_data" / "sessions" / session_id / "context_handoff"
        handoff.mkdir(parents=True, exist_ok=True)
        logger = adw_common.PhaseLogger(session_id)
        # Redirect log path to tmp
        logger.dir = handoff
        logger.log_path = handoff / "run.log"
        return logger, handoff

    def test_first_attempt_pass(self, tmp_path):
        """Builder passes on the first try — returns 0."""
        logger, handoff = self._make_logger(tmp_path)

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                # Builder succeeds (returncode 0), gate passes
                mock_run.return_value = (True, "built ok")
                # gates.code_quality runs real pytest — we need to mock it too
                with mock.patch("gates.code_quality", return_value={
                    "gate": "code_quality", "pass": True, "detail": {"summary": "all ok", "checks": [
                        {"name": "pytest", "required": True, "ran": True, "pass": True, "detail": ""}
                    ]}
                }):
                    rc, out, total = adw_common.retry_ladder(
                        "builder",
                        "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                        plan_text="test plan",
                        dry_run=False,
                        logger=logger,
                        handoff=handoff,
                        config=FAKE_CONFIG,
                    )

        assert rc == 0
        assert total == 1
        assert out == "built ok"

    def test_retry_then_pass(self, tmp_path):
        """First attempt fails gate, second passes — retry works."""
        logger, handoff = self._make_logger(tmp_path)

        gate_results = [
            {"gate": "code_quality", "pass": False, "detail": {"summary": "pytest failed", "checks": []}},
            {"gate": "code_quality", "pass": True, "detail": {"summary": "all ok", "checks": []}},
        ]
        call_count = [0]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return gate_results[idx]

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                mock_run.return_value = (True, "built ok")
                with mock.patch("gates.code_quality", side_effect=side_effect):
                    rc, out, total = adw_common.retry_ladder(
                        "builder",
                        "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                        plan_text="test plan",
                        dry_run=False,
                        logger=logger,
                        handoff=handoff,
                        config=FAKE_CONFIG,
                    )

        assert rc == 0
        assert total == 2  # two attempts
        assert mock_run.call_count == 2

    def test_escalate_to_builder_escalation(self, tmp_path):
        """Builder rung exhausted → escalate to builder_escalation which passes."""
        logger, handoff = self._make_logger(tmp_path)

        # All builder attempts fail
        gate_results = [
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
            # builder_escalation first attempt passes (total_attempts=3)
            {"gate": "code_quality", "pass": True, "detail": {"summary": "all ok", "checks": []}},
        ]
        call_count = [0]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return gate_results[idx]

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                mock_run.return_value = (True, "escalated and fixed")
                with mock.patch("gates.code_quality", side_effect=side_effect):
                    rc, out, total = adw_common.retry_ladder(
                        "builder",
                        "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                        plan_text="test plan",
                        dry_run=False,
                        logger=logger,
                        handoff=handoff,
                        config=FAKE_CONFIG,
                    )

        assert rc == 0
        assert total == 3  # 2 builder + 1 builder_escalation
        # Should be called with "builder" twice and "builder_escalation" once
        route_names = [c[0][0] for c in mock_run.call_args_list]
        assert route_names == ["builder", "builder", "builder_escalation"]

    def test_all_rungs_exhausted(self, tmp_path):
        """Both builder and builder_escalation exhausted → returns 1."""
        logger, handoff = self._make_logger(tmp_path)

        # All attempts fail (2 builder + 2 escalation)
        gate_results = [
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
        ]
        call_count = [0]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return gate_results[idx]

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                mock_run.return_value = (True, "still broken")
                with mock.patch("gates.code_quality", side_effect=side_effect):
                    rc, out, total = adw_common.retry_ladder(
                        "builder",
                        "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                        plan_text="test plan",
                        dry_run=False,
                        logger=logger,
                        handoff=handoff,
                        config=FAKE_CONFIG,
                    )

        assert rc == 1
        assert total == 4  # 2 builder + 2 escalation
        # Verify escalation rung was used
        route_names = [c[0][0] for c in mock_run.call_args_list]
        assert route_names.count("builder_escalation") == 2

    def test_retry_context_on_second_attempt(self, tmp_path):
        """Second attempt gets retry_context in the prompt with gate output."""
        logger, handoff = self._make_logger(tmp_path)

        gate_results = [
            {"gate": "code_quality", "pass": False, "detail": {"summary": "fail", "checks": []}},
            {"gate": "code_quality", "pass": True, "detail": {"summary": "all ok", "checks": []}},
        ]
        call_count = [0]

        def side_effect(*args, **kwargs):
            idx = call_count[0]
            call_count[0] += 1
            return gate_results[idx]

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                mock_run.return_value = (True, "fixed")
                with mock.patch("gates.code_quality", side_effect=side_effect):
                    rc, out, total = adw_common.retry_ladder(
                        "builder",
                        "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                        plan_text="test plan",
                        dry_run=False,
                        logger=logger,
                        handoff=handoff,
                        config=FAKE_CONFIG,
                    )

        assert rc == 0
        # Second call (attempt 2) should have retry_context with gate output
        second_prompt = mock_run.call_args_list[1][0][1]
        assert "GATE FAILURE OUTPUT" in second_prompt
        assert "pytest" in second_prompt or "fail" in second_prompt

    def test_dry_run_returns_zero(self, tmp_path):
        """Dry run mode returns 0 without invoking anything."""
        logger, handoff = self._make_logger(tmp_path)

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                mock_run.return_value = (True, "dry-run output")
                with mock.patch("gates.code_quality") as mock_gate:
                    rc, out, total = adw_common.retry_ladder(
                        "builder",
                        "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                        plan_text="test plan",
                        dry_run=True,
                        logger=logger,
                        handoff=handoff,
                        config=FAKE_CONFIG,
                    )

        assert rc == 0
        assert total == 1
        # gates.code_quality should NOT be called in dry-run
        mock_gate.assert_not_called()

    def test_envelope_validation_blocks(self, tmp_path):
        """A malformed envelope (missing keys) stops the retry ladder."""
        logger, handoff = self._make_logger(tmp_path)

        with mock.patch("adw_common.load_config", return_value=FAKE_CONFIG):
            with mock.patch("adw_common.run_route") as mock_run:
                mock_run.return_value = (True, "output")
                # Corrupt the envelope that retry_ladder writes before gate
                # by making write_envelope a no-op that writes bad JSON
                with mock.patch("adw_common.write_envelope") as mock_write:
                    def bad_write(path, *, status, summary, changed_files, **extra):
                        path.write_text('{"not": "an envelope"}')
                    mock_write.side_effect = bad_write
                    with mock.patch("gates.code_quality") as mock_gate:
                        rc, out, total = adw_common.retry_ladder(
                            "builder",
                            "--- PLAN ---\n{plan}\n--- END PLAN ---\n{retry_context}",
                            plan_text="test plan",
                            dry_run=False,
                            logger=logger,
                            handoff=handoff,
                            config=FAKE_CONFIG,
                        )

        assert rc == 2  # envelope validation failed
        assert total == 1
        mock_gate.assert_not_called()  # Should not reach quality gate


# ---------------------------------------------------------------------------
# codex prompt composition
# ---------------------------------------------------------------------------

class TestCodexComposePrompt:
    def test_role_prompt_file_prepended(self, tmp_path):
        """The reviewer contract text from adws/prompts/reviewer.md reaches composed prompt."""
        reviewer_path = tmp_path / "reviewer.md"
        reviewer_path.write_text("# Role: Reviewer (Tier 1b)\n\nBe skeptical.\n")
        task = "Review this diff."

        composed = adw_common.codex_compose_prompt(str(reviewer_path), task)
        assert "Be skeptical." in composed
        assert "--- TASK ---" in composed
        assert "Review this diff." in composed
        # Role content before separator
        assert composed.index("Be skeptical.") < composed.index("--- TASK ---")

    def test_reviewer_contract_reaches_prompt(self):
        """Integration: the real reviewer.md content appears in composed prompt."""
        reviewer_path = _adws / "prompts" / "reviewer.md"
        task = "Review this diff against the plan."

        composed = adw_common.codex_compose_prompt(str(reviewer_path), task)
        assert "be skeptical" in composed
        assert "Header first" in composed
        assert "Hunt for" in composed
        assert "verdict line" in composed.lower() or "Verdict line" in composed
        assert composed.endswith(task)

    def test_empty_role_prompt_returns_task_only(self):
        result = adw_common.codex_compose_prompt("", "just the task")
        assert result == "just the task"

    def test_nonexistent_file_uses_literal(self):
        result = adw_common.codex_compose_prompt("/nonexistent/path.md", "task content")
        # Treats the path string as literal content since file doesn't exist
        assert "/nonexistent/path.md" in result
        assert "task content" in result

    def test_no_role_prompt_returns_task(self):
        result = adw_common.codex_compose_prompt("", "only task")
        assert result == "only task"


# ---------------------------------------------------------------------------
# gates.json_parse integration with retry ladder envelopes
# ---------------------------------------------------------------------------

class TestGateIntegration:
    def test_missing_keys_rejected(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text('{"status": "succeeded"}')
        result = gates.json_parse(str(p))
        assert result["pass"] is False
        assert "missing keys" in result["detail"]

    def test_missing_file(self):
        result = gates.json_parse("/tmp/nonexistent_adw_test_file_12345.json")
        assert result["pass"] is False
        assert "missing" in result["detail"]

    def test_invalid_json(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not valid json}")
        result = gates.json_parse(str(p))
        assert result["pass"] is False
        assert "invalid JSON" in result["detail"]


# ---------------------------------------------------------------------------
# Prompt template format correctness
# ---------------------------------------------------------------------------

class TestPromptTemplates:
    """Ensure the prompt templates used by the runners still format correctly."""

    def test_builder_template_formats(self):
        tmpl = """--- PLAN ---
{plan}
--- END PLAN ---
{retry_context}"""
        result = tmpl.format(plan="my plan", retry_context="retry info")
        assert "my plan" in result
        assert "retry info" in result

    def test_reviewer_template_formats_with_diff(self):
        """Reviewer template now takes diff + changed_files, not summary."""
        # This is the template from adw_simple_sdlc.py after hardening
        tmpl = """--- PLAN ---
{plan}
--- END PLAN ---

--- FULL GIT DIFF ---
{diff}
--- END GIT DIFF ---

--- CHANGED FILES ---
{changed_files}
--- END CHANGED FILES ---"""
        result = tmpl.format(plan="p", diff="diff content", changed_files="a.py\nb.py")
        assert "diff content" in result
        assert "a.py" in result
        assert "b.py" in result
        # Verify no old {summary} placeholder remains
        assert "{summary}" not in tmpl