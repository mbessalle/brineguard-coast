#!/usr/bin/env python3
"""Uniform backend prober — the reusable "does this model route actually work?" tool.

Each backend is one data row: an argv template plus how it gets its key. The
runner sends the same sentinel prompt everywhere and greps the reply, so any
new backend/model that shows up is a one-line row edit, not new code.

Usage:
  python3 tools/probe.py                          # probe every backend row
  python3 tools/probe.py pi openrouter            # probe selected rows
  python3 tools/probe.py pi --model moonshotai/kimi-k3   # override the row's model
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrouter_call import load_key as openrouter_key  # noqa: E402

SENTINEL = "PROBE-OK-7391"
PROMPT = f"Reply with exactly: {SENTINEL}"


def gemini_key() -> str:
    return open(".env.gemini_key", encoding="utf-8").read().strip()


# backend -> (argv template, extra-env builder). {model}/{prompt} are substituted.
# Add a backend or change a default model by editing rows only.
BACKENDS: dict[str, dict] = {
    "claude":     {"argv": ["claude", "-p", "--model", "{model}", "{prompt}"],
                   "model": "haiku", "env": None},
    "codex":      {"argv": ["codex", "exec", "--skip-git-repo-check", "{prompt}"],
                   "model": "(codex default)", "env": None},
    "pi":         {"argv": ["pi", "--provider", "openrouter", "--model", "{model}",
                            "-p", "--no-session", "{prompt}"],
                   "model": "deepseek/deepseek-v4-pro",
                   "env": lambda: {"OPENROUTER_API_KEY": openrouter_key()}},
    "pi-google":  {"argv": ["pi", "-p", "--no-session", "{prompt}"],
                   "model": "(pi default gemini)", "env": None},
    "openrouter": {"argv": [sys.executable, "tools/openrouter_call.py", "chat",
                            "-m", "{model}", "{prompt}"],
                   "model": "deepseek/deepseek-v4-flash", "env": None},
    "gemini":     {"argv": [sys.executable, "tools/gemini_flash.py", "{prompt}"],
                   "model": "(gemini-3.7-flash)",
                   "env": lambda: {"GEMINI_API_KEY": gemini_key()}},
}


def probe(name: str, model_override: str | None, timeout: int) -> dict:
    row = BACKENDS[name]
    model = model_override or row["model"]
    argv = [a.format(model=model, prompt=PROMPT) for a in row["argv"]]
    env = {**os.environ, **(row["env"]() if row["env"] else {})}
    start = time.monotonic()
    try:
        r = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout)
        ok = SENTINEL in r.stdout
        detail = "" if ok else (r.stdout.strip() or r.stderr.strip())[:120]
    except Exception as e:  # missing binary, timeout, key error
        ok, detail = False, str(e)[:120]
    return {"backend": name, "model": model, "pass": ok,
            "seconds": round(time.monotonic() - start, 1), "detail": detail}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backends", nargs="*", help=f"subset of {list(BACKENDS)}; default all")
    parser.add_argument("--model", help="override the row's default model")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    names = args.backends or list(BACKENDS)
    unknown = set(names) - set(BACKENDS)
    if unknown:
        sys.exit(f"unknown backends: {sorted(unknown)}; known: {list(BACKENDS)}")
    failures = 0
    for name in names:
        result = probe(name, args.model, args.timeout)
        status = "PASS" if result["pass"] else "FAIL"
        failures += not result["pass"]
        print(f"{status}  {result['backend']:11} {result['model']:35} "
              f"{result['seconds']:6.1f}s  {result['detail']}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
