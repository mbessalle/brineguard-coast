#!/usr/bin/env python3
"""Model-identity preflight: verify a requested model EXISTS in its backend's
catalog before any agent spawn. Blocks silent fallback (pi downgraded
gpt-5.6-sol -> gpt-5.5 without failing; caught by the user, not the tooling).

Template table: one row per provider; adding a provider is a row edit.
Catalog results are cached 10 minutes in /tmp so the check costs ~0s.

Usage:
  python3 tools/model_preflight.py check <provider> <model>     exit 0 ok, 1 missing
  python3 tools/model_preflight.py hook                          Claude Code PreToolUse
      (reads hook JSON on stdin; denies Bash commands that invoke
       `pi --provider P --model M` with a model absent from P's catalog)
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

CACHE_TTL_S = 600
# user-owned cache dir, not world-writable /tmp (audit X9)
CACHE_DIR = Path.home() / ".cache" / "model_preflight"

# provider -> argv that prints the catalog (one model id per line after filtering)
PROVIDERS: dict[str, dict] = {
    "openai-codex": {
        "cmd": ["pi", "--provider", "openai-codex", "--list-models"],
        "filter": lambda line: line.split()[1] if line.strip().startswith("openai-codex") else None,
    },
    "openrouter": {
        "cmd": ["python3", str(Path(__file__).parent / "openrouter_call.py"), "models"],
        "filter": lambda line: line.strip().split()[0] if line.strip() else None,
    },
}


def catalog(provider: str) -> set[str] | None:
    """Return the provider's model-id set, cached. None = catalog unavailable
    (fail open with a warning; an outage must not block all work)."""
    row = PROVIDERS.get(provider)
    if row is None:
        return None  # unknown provider: not our jurisdiction
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache = CACHE_DIR / f"{provider}.txt"
    if cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL_S:
        return set(cache.read_text().split())
    try:
        # pi prints the catalog on stderr; merge streams before filtering
        proc = subprocess.run(row["cmd"], stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, text=True, timeout=30)
        if proc.returncode != 0:  # never cache a failing CLI's output (X16)
            return None
        ids = {m for line in proc.stdout.splitlines() if (m := row["filter"](line))}
    except Exception:
        return None
    if ids:
        cache.write_text("\n".join(sorted(ids)))
        return ids
    return None


def check(provider: str, model: str) -> tuple[bool, str]:
    """Fail CLOSED (audit X6): an unverifiable model blocks the spawn unless
    MODEL_PREFLIGHT_ALLOW_UNVERIFIED=1 is set explicitly for that call."""
    import os
    override = os.environ.get("MODEL_PREFLIGHT_ALLOW_UNVERIFIED") == "1"
    ids = catalog(provider)
    if ids is None:
        if provider not in PROVIDERS:
            return True, f"OK: provider '{provider}' validates models server-side or is out of scope"
        if override:
            return True, f"WARN: catalog for '{provider}' unavailable; UNVERIFIED spawn allowed by explicit override"
        return False, (f"BLOCKED: catalog for '{provider}' unavailable; cannot verify "
                       f"'{model}'. Set MODEL_PREFLIGHT_ALLOW_UNVERIFIED=1 to override knowingly.")
    if model in ids:
        return True, f"OK: {provider}/{model} present in catalog ({len(ids)} models)"
    return False, (f"BLOCKED: model '{model}' NOT in {provider} catalog. The runtime "
                   f"would silently fall back to another model. Closest available: "
                   f"{sorted(m for m in ids if m[:5] == model[:5]) or sorted(ids)[-3:]}")


def hook() -> int:
    """PreToolUse hook: deny pi spawns whose --model is absent from the catalog."""
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    # order-insensitive, tolerates --flag=value (audit X7); scoped to pi
    # launches — codex validates server-side with a hard 400
    if not re.search(r"(^|[\s|;&(])pi\s", cmd):
        return 0
    pm = re.search(r"--provider[=\s]+(\S+)", cmd)
    mm = re.search(r"--model[=\s]+(\S+)", cmd)
    if not (pm and mm):
        return 0
    ok, msg = check(pm.group(1).strip("'\""), mm.group(1).strip("'\"").split(":")[0])
    if not ok:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": msg}}))
    return 0


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "hook":
        return hook()
    if len(sys.argv) == 4 and sys.argv[1] == "check":
        ok, msg = check(sys.argv[2], sys.argv[3])
        print(msg)
        return 0 if ok else 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
