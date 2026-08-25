#!/usr/bin/env python3
"""Model-drift detector — diffs pinned SSSF routes against live model catalogs.

Every session start (via session_brief.sh) checks whether a newer model exists
in the same family as each pinned route. Pulls the live OpenRouter catalog once
and reads ~/.codex/models_cache.json for codex-cli routes. Exit 0 always.

Usage:
  python3 tools/model_freshness.py              # human-readable report
  python3 tools/model_freshness.py --json       # JSON (machines)
  python3 tools/model_freshness.py --config /tmp/doctored.yaml  # test override
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrouter_call import request as or_request, load_key as or_load_key  # noqa: E402

# Model-family prefixes ordered from most-specific to least-specific.
# Derived by running the model id up to and including the "family word"
# (e.g. "deepseek/deepseek-v", "qwen/qwen", "moonshotai/kimi-k").
FAMILY_PREFIXES = [
    "deepseek/deepseek-v",
    "qwen/qwen",
    "qwen/qwq-",
    "moonshotai/kimi-k",
    "openai/gpt-5-",           # gpt-5-mini, gpt-5-nano (fixed-tier, before broad gpt-)
    "openai/gpt-",
    "google/gemini-",
    "nvidia/nemotron-",
    "meta-llama/llama-",
    "anthropic/claude-",
    "mistralai/mistral-",
    "mistralai/codestral-",
    "gpt-",                     # codex-cli bare slug (no org/ prefix)
]

DOT_VERSION = re.compile(r"\d+(?:\.\d+)*")
# Date-suffixed snapshots: compact (20250728), ISO (2025-07-28), month-day (0731),
# year-month (2507).  Stripped repeatedly from the remainder after family prefix.
_DATE = re.compile(
    r"-\d{4}-\d{2}-\d{2}"       # 2025-07-28
    r"|-\d{8}"                     # 20250728
    r"|-\d{4}$"                    # -0731  (month-day at end)
    r"|-\d{6}$"                    # -2507  (year-month at end)
)
VARIANTS = (":free", ":batch", "-latest", "~", ":thinking")


def family_for(model_id: str) -> str:
    """Return the longest matching family prefix, or the raw id if none match."""
    for prefix in FAMILY_PREFIXES:
        if model_id.startswith(prefix):
            return prefix
    return model_id


def _strip_dates(s: str) -> str:
    """Remove date-suffixed snapshots from *s*, applied repeatedly."""
    while True:
        m = _DATE.search(s)
        if not m:
            return s
        s = s[: m.start()] + s[m.end():]


def version_tuple(model_id: str, family: str) -> tuple[int, ...]:
    """Parse numeric dot-tokens (e.g. "3.8", "4") after stripping family, dates, variants."""
    remainder = model_id[len(family):]
    remainder = _strip_dates(remainder)
    for variant in VARIANTS:
        if remainder.endswith(variant):
            remainder = remainder[:-len(variant)]
    # Extract the first dot-separated version pattern
    m = DOT_VERSION.search(remainder)
    if not m:
        return ()
    return tuple(int(x) for x in m.group().split("."))


def load_config(path: str) -> dict:
    """Minimal YAML loader for sssf.config.yaml — key-value top-level, limited depth."""
    import yaml  # lazy — pyyaml is in .venv
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def pinned_routes(config: dict) -> list[dict]:
    """Return route entries with openrouter-api / pi-openrouter / codex-cli backends."""
    routes = config.get("routes", {})
    pinned = []
    for name, spec in routes.items():
        backend = spec.get("backend", "")
        if backend in ("openrouter-api", "pi-openrouter", "codex-cli"):
            pinned.append({"route": name, "model": spec["model"], "backend": backend})
    return pinned


def or_catalog() -> list[str] | None:
    """Fetch the live OpenRouter model catalog.  Returns list of ids or None on failure."""
    try:
        or_load_key()
        data = or_request("/models")
        return [r["id"] for r in data["data"]]
    except (Exception, SystemExit) as exc:
        print(f"freshness check skipped: OpenRouter API unreachable ({exc})", file=sys.stderr)
        return None


def codex_catalog() -> list[str] | None:
    """Read model slugs from ~/.codex/models_cache.json.  Returns list or None."""
    cache_path = os.path.expanduser("~/.codex/models_cache.json")
    try:
        with open(cache_path, encoding="utf-8") as fh:
            data = json.load(fh)
        return sorted(m["slug"] for m in data.get("models", []))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"freshness check skipped: codex cache unreadable ({exc})", file=sys.stderr)
        return None


def find_newer(pinned: str, live_ids: list[str]) -> list[str]:
    """Return *live_ids* in the same family as *pinned* with a strictly higher version."""
    fam = family_for(pinned)
    pinned_ver = version_tuple(pinned, fam)
    newer = []
    for live in live_ids:
        if not live.startswith(fam):
            continue
        live_ver = version_tuple(live, fam)
        if live_ver > pinned_ver:
            newer.append(live)
    return sorted(newer)


def run(config_path: str) -> dict:
    """Run freshness check and return structured result."""
    config = load_config(config_path)
    routes = pinned_routes(config)

    or_ids: list[str] | None = None
    codex_ids: list[str] | None = None

    or_routes = [r for r in routes if r["backend"] in ("openrouter-api", "pi-openrouter")]
    codex_routes = [r for r in routes if r["backend"] == "codex-cli"]

    if or_routes:
        or_ids = or_catalog()

    if codex_routes:
        codex_ids = codex_catalog()

    drift_lines: list[dict] = []
    for r in or_routes:
        if or_ids is None:
            break  # catalog fetch failed — already printed skip message
        newer = find_newer(r["model"], or_ids)
        if newer:
            drift_lines.append({
                "route": r["route"],
                "pinned": r["model"],
                "newer": newer,
            })

    for r in codex_routes:
        if codex_ids is None:
            break
        newer = find_newer(r["model"], codex_ids)
        if newer:
            drift_lines.append({
                "route": r["route"],
                "pinned": r["model"],
                "newer": newer,
            })

    return {"drifts": drift_lines, "or_ok": or_ids is not None, "codex_ok": codex_ids is not None}


def main() -> None:
    parser = argparse.ArgumentParser(description="Model-drift detector")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--config", default="sssf.config.yaml", help="path to sssf config")
    args = parser.parse_args()

    result = run(args.config)

    if args.json:
        json.dump(result, sys.stdout, indent=2)
        return

    for d in result["drifts"]:
        newer_str = ",".join(d["newer"])
        print(f"DRIFT {d['route']} pinned={d['pinned']} newer={newer_str}")

    n = len(result["drifts"])
    if n == 0:
        print("model freshness: all pinned routes current")
    else:
        print(f"model freshness: {n} drift(s)")


if __name__ == "__main__":
    main()