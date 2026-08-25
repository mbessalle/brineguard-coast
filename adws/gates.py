"""Deterministic quality gates for SSSF ADWs.

Tier 3 of the tiered model stack (see sssf.config.yaml): zero-token,
local-only checks. These functions are called directly by the ADW runner
scripts between LLM phases, and are also exposed as a CLI for manual/CI use.

Every gate returns a dict of the shape:
    {"gate": <name>, "pass": <bool>, "detail": <str | dict>}

Only stdlib + repo deps are used here. Do not add dependencies.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PYTHON = REPO_ROOT / ".venv" / "bin" / "python"

REQUIRED_ENVELOPE_KEYS = ("status", "summary", "changed_files")


def _resolve(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (REPO_ROOT / p)


def artifacts_exist(paths: list[str]) -> dict:
    """Check that every path in `paths` exists (file or directory)."""
    missing = [str(p) for p in paths if not _resolve(p).exists()]
    ok = not missing
    detail = "all artifacts present" if ok else f"missing: {missing}"
    return {"gate": "artifacts_exist", "pass": ok, "detail": detail}


def files_non_empty(paths: list[str]) -> dict:
    """Check that every path in `paths` exists AND has non-zero size."""
    problems = []
    for p in paths:
        resolved = _resolve(p)
        if not resolved.exists():
            problems.append(f"{p}: missing")
        elif resolved.is_file() and resolved.stat().st_size == 0:
            problems.append(f"{p}: empty")
    ok = not problems
    detail = "all files present and non-empty" if ok else f"problems: {problems}"
    return {"gate": "files_non_empty", "pass": ok, "detail": detail}


def json_parse(path: str) -> dict:
    """Parse `path` as JSON and validate it is a phase envelope.

    A valid envelope is a JSON object containing at least the keys
    "status", "summary", and "changed_files".
    """
    resolved = _resolve(path)
    if not resolved.exists():
        return {"gate": "json_parse", "pass": False, "detail": f"{path}: missing"}

    try:
        text = resolved.read_text()
        data = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        return {"gate": "json_parse", "pass": False, "detail": f"{path}: invalid JSON ({exc})"}

    if not isinstance(data, dict):
        return {
            "gate": "json_parse",
            "pass": False,
            "detail": f"{path}: top-level JSON must be an object, got {type(data).__name__}",
        }

    missing_keys = [k for k in REQUIRED_ENVELOPE_KEYS if k not in data]
    if missing_keys:
        return {
            "gate": "json_parse",
            "pass": False,
            "detail": f"{path}: envelope missing keys {missing_keys}",
        }

    problems = []
    if data["status"] not in ("succeeded", "failed"):
        problems.append(f"status must be 'succeeded' or 'failed', got {data['status']!r}")
    if not isinstance(data["summary"], str) or not data["summary"].strip():
        problems.append("summary must be a non-empty string")
    if not isinstance(data["changed_files"], list) or not all(
        isinstance(p, str) for p in data["changed_files"]
    ):
        problems.append("changed_files must be a list of strings")
    if problems:
        return {"gate": "json_parse", "pass": False, "detail": f"{path}: {'; '.join(problems)}"}
    if data["status"] == "failed":
        return {
            "gate": "json_parse",
            "pass": False,
            "detail": f"{path}: well-formed envelope but status=failed: {data['summary'][:200]}",
        }

    return {"gate": "json_parse", "pass": True, "detail": f"{path}: valid envelope"}


def _run_check(python: Path, args: list[str], cwd: Path) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            [str(python), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=600,
        )
    except FileNotFoundError as exc:
        return False, f"could not execute {python}: {exc}"
    except subprocess.TimeoutExpired:
        return False, "timed out after 600s"

    ok = proc.returncode == 0
    tail_out = proc.stdout[-4000:] if proc.stdout else ""
    tail_err = proc.stderr[-4000:] if proc.stderr else ""
    detail = f"exit={proc.returncode}\nstdout:\n{tail_out}\nstderr:\n{tail_err}"
    return ok, detail


def _module_available(python: Path, module: str) -> bool:
    try:
        proc = subprocess.run(
            [str(python), "-c", f"import {module}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def code_quality(python: str | Path | None = None, cwd: str | Path | None = None) -> dict:
    """Run the deterministic quality suite: pytest (required) plus
    ruff/mypy (best-effort, skipped gracefully if not installed).

    Never installs anything. Returns one aggregate gate dict with a
    per-check breakdown in `detail["checks"]`.
    """
    py = Path(python) if python else DEFAULT_PYTHON
    root = Path(cwd) if cwd else REPO_ROOT

    checks: list[dict] = []

    # pytest: always required.
    ok, detail = _run_check(py, ["-m", "pytest"], root)
    checks.append({"name": "pytest", "required": True, "ran": True, "pass": ok, "detail": detail})

    # ruff: best-effort.
    if _module_available(py, "ruff"):
        ok, detail = _run_check(py, ["-m", "ruff", "check", "."], root)
        checks.append({"name": "ruff", "required": False, "ran": True, "pass": ok, "detail": detail})
    else:
        checks.append(
            {
                "name": "ruff",
                "required": False,
                "ran": False,
                "pass": True,
                "detail": "ruff not installed; skipped (not adding dependencies)",
            }
        )

    # mypy: best-effort.
    if _module_available(py, "mypy"):
        ok, detail = _run_check(py, ["-m", "mypy", "src"], root)
        checks.append({"name": "mypy", "required": False, "ran": True, "pass": ok, "detail": detail})
    else:
        checks.append(
            {
                "name": "mypy",
                "required": False,
                "ran": False,
                "pass": True,
                "detail": "mypy not installed; skipped (not adding dependencies)",
            }
        )

    # Overall pass = every *required* check passed. A best-effort check that
    # ran and failed is surfaced but does not fail the gate; pytest failing
    # always fails the gate.
    required_failed = [c["name"] for c in checks if c["required"] and not c["pass"]]
    optional_failed = [c["name"] for c in checks if not c["required"] and c["ran"] and not c["pass"]]

    overall_pass = not required_failed
    summary_bits = []
    if required_failed:
        summary_bits.append(f"required checks failed: {required_failed}")
    if optional_failed:
        summary_bits.append(f"optional checks failed (non-blocking): {optional_failed}")
    if not summary_bits:
        summary_bits.append("all checks passed")

    return {
        "gate": "code_quality",
        "pass": overall_pass,
        "detail": {"summary": "; ".join(summary_bits), "checks": checks},
    }


def _print_result(result: dict) -> None:
    printable = dict(result)
    detail = printable.get("detail")
    if isinstance(detail, dict):
        printable = {**printable, "detail": detail}
        print(json.dumps(printable, indent=2, default=str))
    else:
        print(json.dumps(printable, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gates.py",
        description="Tier 3 deterministic quality gates for SSSF ADWs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_artifacts = sub.add_parser("artifacts", help="Check that paths exist.")
    p_artifacts.add_argument("paths", nargs="+")

    p_nonempty = sub.add_parser("nonempty", help="Check that paths exist and are non-empty.")
    p_nonempty.add_argument("paths", nargs="+")

    p_json = sub.add_parser("json", help="Validate a JSON phase envelope.")
    p_json.add_argument("path")

    p_quality = sub.add_parser("quality", help="Run pytest + ruff/mypy (if installed).")
    p_quality.add_argument("--python", default=None, help="Path to python interpreter (default: .venv/bin/python)")

    args = parser.parse_args(argv)

    if args.command == "artifacts":
        result = artifacts_exist(args.paths)
    elif args.command == "nonempty":
        result = files_non_empty(args.paths)
    elif args.command == "json":
        result = json_parse(args.path)
    elif args.command == "quality":
        result = code_quality(python=args.python)
    else:  # pragma: no cover - argparse guards this
        parser.error(f"unknown command {args.command!r}")
        return 2

    _print_result(result)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
