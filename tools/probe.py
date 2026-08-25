#!/usr/bin/env python3
"""Uniform backend prober — the reusable "does this model route actually work?" tool.

Probe targets are auto-generated from sssf.config.yaml routes (every route
with a callable backend). Rows run concurrently (cap 4). A route passes only
when BOTH the sentinel appears in stdout AND the subprocess exit code is 0.

Usage:
  python3 tools/probe.py                          # probe every callable route
  python3 tools/probe.py builder scout            # probe selected routes
  python3 tools/probe.py builder --model moonshotai/kimi-k3   # override model
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrouter_call import load_key as openrouter_key  # noqa: E402

CONFIG = Path(__file__).parent.parent / "sssf.config.yaml"
SENTINEL = "PROBE-OK-7391"
PROMPT = f"Reply with exactly: {SENTINEL}"


def _load_config() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh.read())


def _env_for_backend(backend_name: str):
    """Return an env builder callable for known backends that need keys."""
    if backend_name == "pi-openrouter":
        return lambda: {"OPENROUTER_API_KEY": openrouter_key()}
    return None


def _build_targets(config: dict, route_filter: set[str] | None = None) -> dict[str, dict]:
    """Build probe targets from sssf.config.yaml routes with callable backends."""
    backends_cfg = config.get("backends", {})
    routes_cfg = config.get("routes", {})
    targets: dict[str, dict] = {}
    for route_name, route_cfg in routes_cfg.items():
        if route_filter is not None and route_name not in route_filter:
            continue
        backend_name = route_cfg.get("backend", "")
        backend_cfg = backends_cfg.get(backend_name, {})
        invoke = backend_cfg.get("invoke")
        if not isinstance(invoke, list):
            continue  # session or other non-callable backend
        model = route_cfg.get("model", "")
        # Build argv: substitute {model}/{prompt}; drop {role_prompt} and the
        # flag that introduces it (e.g. -s / --append-system-prompt).
        argv: list[str] = []
        for arg in invoke:
            if "{role_prompt}" in arg:
                if argv and argv[-1].startswith("-"):
                    argv.pop()  # drop the orphaned flag that introduced it
                continue
            fmtd = arg.format(model=model, prompt=PROMPT, role_prompt="")
            # Replace bare 'python3' with sys.executable for reliability
            if fmtd == "python3":
                fmtd = sys.executable
            argv.append(fmtd)
        targets[route_name] = {
            "argv": argv,
            "model": model,
            "env": _env_for_backend(backend_name),
        }
    return targets


def probe(route_name: str, target: dict, model_override: str | None,
          timeout: int) -> dict:
    """Run one probe. Passes only if sentinel found AND exit code is 0."""
    model = model_override or target["model"]
    argv = [a.replace(target["model"], model) if target["model"] in a else a
            for a in target["argv"]]
    env = {**os.environ, **(target["env"]() if target["env"] else {})}
    start = time.monotonic()
    try:
        r = subprocess.run(argv, env=env, capture_output=True, text=True,
                           timeout=timeout)
        ok = SENTINEL in r.stdout and r.returncode == 0
        detail = "" if ok else (r.stdout.strip() or r.stderr.strip())[:120]
    except Exception as e:
        ok, detail = False, str(e)[:120]
    return {"backend": route_name, "model": model, "pass": ok,
            "seconds": round(time.monotonic() - start, 1), "detail": detail}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("routes", nargs="*",
                        help="subset of callable route names; default all")
    parser.add_argument("--model", help="override the route's default model")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    config = _load_config()
    route_filter = set(args.routes) if args.routes else None
    targets = _build_targets(config, route_filter)

    if args.routes:
        unknown = set(args.routes) - set(targets)
        if unknown:
            sys.exit(f"unknown/uncallable routes: {sorted(unknown)}")

    if not targets:
        print("No callable routes found in config (all skipped or non-callable)")
        sys.exit(0)

    failures = 0
    max_workers = min(len(targets), 4)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        futs = {pool.submit(probe, name, tgt, args.model, args.timeout): name
                for name, tgt in targets.items()}
        for fut in concurrent.futures.as_completed(futs):
            result = fut.result()
            status = "PASS" if result["pass"] else "FAIL"
            failures += not result["pass"]
            print(f"{status}  {result['backend']:22} {result['model']:35} "
                  f"{result['seconds']:6.1f}s  {result['detail']}")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()