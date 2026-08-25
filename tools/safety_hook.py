#!/usr/bin/env python3
"""PreToolUse safety checkpoint (adopted from disler/claude-code-hooks-mastery).

Deterministically blocks two command classes the repo rules currently forbid
only in prose:
  1. Key exposure: commands that would print .env* contents into output/logs
     (cat/less/head/tail/grep/echo/strings on .env files). Keys must never
     appear in logs — CLAUDE.md rule, now enforced.
  2. Recursive force-delete of critical roots: rm -rf on /, ~, the repo root,
     runs/, evidence/, data/registry, or .git.

Reads the hook JSON on stdin; prints a deny decision when matched; silent
otherwise. Loading .env via tools/openrouter_call.py:load_key stays allowed
(it never echoes the key).
"""
from __future__ import annotations

import json
import re
import sys

ENV_READERS = r"(?:cat|less|more|head|tail|grep|egrep|awk|sed|echo|strings|xxd|od)"
ENV_PATTERN = re.compile(rf"\b{ENV_READERS}\b[^|;&]*\.env\b")
RM_PATTERN = re.compile(
    r"\brm\s+(-[a-zA-Z]*[rf][a-zA-Z]*\s+)+.*"
    r"(?:(?<![\w/])/(?:\s|$)|~/?(?:\s|$)|\.git\b|\bruns/?\b|\bevidence/?\b|data/registry)"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    cmd = (payload.get("tool_input") or {}).get("command", "")
    reason = None
    if ENV_PATTERN.search(cmd):
        reason = ("Blocked: command would print .env contents into logs. Keys never "
                  "appear in output (CLAUDE.md). Use tools/openrouter_call.py:load_key.")
    elif RM_PATTERN.search(cmd):
        reason = ("Blocked: recursive delete targets a critical root (repo/evidence/"
                  "runs/registry/.git). Name exact files instead.")
    if reason:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
