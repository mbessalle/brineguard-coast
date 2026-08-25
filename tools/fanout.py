#!/usr/bin/env python3
"""Concurrent read-only multi-route fan-out engine — backs /fh-opinion and /fh-debate.

Each route resolves to a chat-only OpenRouter API call (no agentic paths).
Routes on backends session/codex-cli are skipped with a printed reason.
Output is anonymized (aliases only, never real model names in saved files).

Usage:
  python3 tools/fanout.py --prompt "Tell me about Python" [--routes builder,scout]
  python3 tools/fanout.py --prompt-file question.txt
  python3 tools/fanout.py --prompt "x" --dry-run
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from openrouter_call import request  # noqa: E402

CONFIG = Path(__file__).parent.parent / "sssf.config.yaml"
_DEFAULT_ROUTES = ["builder", "scout", "reviewer_independent", "documenter"]
_SKIP_BACKENDS = {"session", "codex-cli"}
# pi-openai-codex is called one-shot with --no-tools (read-only guarantee holds)
_READ_ONLY_BACKENDS = {"openrouter-api", "pi-openrouter", "pi-openai-codex"}
_PI_ONESHOT_BACKENDS = {"pi-openai-codex"}

# ---- helpers ----------------------------------------------------------------

def _load_config() -> dict:
    with open(CONFIG, encoding="utf-8") as fh:
        return yaml.safe_load(fh.read())


def _sanitize(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name)


def _read_prompt(prompt_text: str | None, prompt_file: str | None) -> str:
    if prompt_text:
        return prompt_text
    return Path(prompt_file).read_text(encoding="utf-8")


def _read_system(system: str | None) -> str | None:
    if not system:
        return None
    path = Path(system)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return system


# ---- target resolution -----------------------------------------------------

def _resolve_targets(route_names: list[str], config: dict) -> list[dict]:
    """Return list of {route, alias, model, config} for each callable route."""
    routes_cfg = config["routes"]
    aliases_cfg = config.get("anonymization", {}).get("aliases", {})
    targets = []
    for name in route_names:
        if name not in routes_cfg:
            print(f"SKIP  {name:20} unknown route")
            continue
        route = routes_cfg[name]
        backend = route.get("backend", "")
        alias = aliases_cfg.get(name, name)
        if backend in _SKIP_BACKENDS:
            print(f"SKIP  {alias:20} backend={backend} (read-only guarantee)")
            continue
        if backend not in _READ_ONLY_BACKENDS:
            print(f"SKIP  {alias:20} backend={backend} (unsupported)")
            continue
        targets.append({"route": name, "alias": alias, "model": route["model"],
                        "config": route})
    return targets


# ---- single-route call ------------------------------------------------------

def _call_pi_oneshot(target: dict, prompt: str, system: str | None,
                     timeout: int) -> dict:
    """One-shot chat via pi subscription CLI (no tools, no session). Fast-recipe
    flags verified 2026-08-25: without --thinking low --no-extensions the call
    exceeded 3 minutes; with them ~20s."""
    import subprocess
    model = target["model"]
    full_prompt = (f"{system}\n\n{prompt}" if system else prompt)
    start = time.monotonic()
    argv = ["pi", "--provider", "openai-codex", "--model", model,
            "--thinking", "low", "--no-extensions", "-p", "--no-session",
            "--no-tools", full_prompt]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            raise RuntimeError(f"pi exit {proc.returncode}: {proc.stderr[-200:]}")
        text = proc.stdout.strip()
    except Exception as exc:
        return {"status": "FAIL", "latency": round(time.monotonic() - start, 1),
                "error": str(exc)[:200], "text": "", "est_cost": 0,
                "prompt_chars": len(full_prompt), "response_chars": 0,
                "actual_model": model}
    return {"status": "PASS", "text": text,
            "latency": round(time.monotonic() - start, 1),
            "est_cost": 0.0,  # subscription: no marginal cost
            "prompt_chars": len(full_prompt), "response_chars": len(text),
            "actual_model": model}


def _call_route(target: dict, prompt: str, system: str | None,
                timeout: int = 180) -> dict:
    """Call one route (OpenRouter chat API, or pi one-shot). Returns result dict."""
    if target["config"].get("backend") in _PI_ONESHOT_BACKENDS:
        return _call_pi_oneshot(target, prompt, system, timeout)
    model = target["model"]
    messages = []
    prompt_chars = len(prompt)
    if system:
        messages.append({"role": "system", "content": system})
        prompt_chars += len(system)
    messages.append({"role": "user", "content": prompt})

    start = time.monotonic()
    try:
        result = request("/chat/completions", {"model": model, "messages": messages})
        text = result["choices"][0]["message"]["content"]
        latency = round(time.monotonic() - start, 1)
        response_chars = len(text)
        actual_model = result.get("model", model)
    except Exception as exc:
        return {"status": "FAIL", "latency": round(time.monotonic() - start, 1),
                "error": str(exc)[:200], "text": "", "est_cost": 0,
                "prompt_chars": prompt_chars, "response_chars": 0,
                "actual_model": model}

    cfg = target["config"]
    est = 0.0
    in_price = cfg.get("usd_per_m_in", 0)
    out_price = cfg.get("usd_per_m_out", 0)
    usage = result.get("usage") or {}
    in_tok = usage.get("prompt_tokens")
    out_tok = usage.get("completion_tokens")
    if in_price or out_price:
        if in_tok is not None and out_tok is not None:  # real usage from the API
            est = (in_tok / 1e6 * in_price) + (out_tok / 1e6 * out_price)
        else:  # chars/4 fallback estimate
            est = (prompt_chars / 4.0 / 1e6 * in_price) + (response_chars / 4.0 / 1e6 * out_price)
    return {"status": "PASS", "text": text, "latency": latency,
            "est_cost": round(est, 6), "prompt_chars": prompt_chars,
            "response_chars": response_chars, "actual_model": actual_model}


# ---- main orchestration -----------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Concurrent read-only multi-route fan-out engine")
    g = parser.add_mutually_exclusive_group(required=True)
    g.add_argument("--prompt", help="Prompt text")
    g.add_argument("--prompt-file", help="Path to file containing prompt")
    parser.add_argument("--routes", default=",".join(_DEFAULT_ROUTES),
                        help=f"Comma-separated route names (default: {','.join(_DEFAULT_ROUTES)})")
    parser.add_argument("--system", help="System prompt text or file path")
    parser.add_argument("--out", help="Output directory (default: adw_data/fanout/<timestamp>)")
    parser.add_argument("--timeout", type=int, default=180, help="Per-route timeout in seconds")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned calls without making any")
    args = parser.parse_args()

    config = _load_config()
    prompt = _read_prompt(args.prompt, args.prompt_file)
    system = _read_system(args.system)
    route_names = [r.strip() for r in args.routes.split(",") if r.strip()]
    targets = _resolve_targets(route_names, config)

    import uuid
    out_dir = Path(args.out) if args.out else Path(
        f"adw_data/fanout/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}")
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print(f"DRY RUN — {len(targets)} route(s), out={out_dir}")
        for t in targets:
            print(f"  {t['alias']:20} route={t['route']} model={t['model']}")
        print("(no API calls made)")
        sys.exit(0)

    if not targets:
        print("FAIL: no callable routes after resolution (all skipped or unknown)")
        sys.exit(1)

    results: list[dict] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(targets)) as pool:
        futs = {pool.submit(_call_route, t, prompt, system, args.timeout): t
                for t in targets}
        # Global deadline: unfinished futures after --timeout become FAILs
        # instead of blocking the whole fan-in on one hung route.
        done, not_done = concurrent.futures.wait(futs, timeout=args.timeout + 10)
        for fut in done:
            t = futs[fut]
            try:
                r = fut.result()
            except Exception as exc:
                r = {"status": "FAIL", "latency": args.timeout,
                     "error": f"worker exception: {exc}"[:200],
                     "text": "", "est_cost": 0, "prompt_chars": len(prompt),
                     "response_chars": 0, "actual_model": t["model"]}
            r.update(alias=t["alias"], route=t["route"], model_cfg=t["model"])
            results.append(r)
        for fut in not_done:
            fut.cancel()
            t = futs[fut]
            results.append({"status": "FAIL", "latency": args.timeout,
                            "error": "deadline exceeded (route hung)", "text": "",
                            "est_cost": 0, "prompt_chars": len(prompt),
                            "response_chars": 0, "actual_model": t["model"],
                            "alias": t["alias"], "route": t["route"],
                            "model_cfg": t["model"]})
        if not_done:
            pool.shutdown(wait=False, cancel_futures=True)

    # Sort for stable output
    results.sort(key=lambda r: r["alias"])

    # ---- write per-route files + collect aggregate ----
    agg_parts: list[str] = []
    metrics_rows: list[dict] = []
    any_pass = False

    for r in results:
        fname = _sanitize(r["alias"]) + ".md"
        body = r["text"] if r["status"] == "PASS" else (
            f"STATUS: FAIL\nERROR: {r.get('error', 'unknown')}")
        content = f"# {r['alias']}\n\n{body}".strip() + "\n"
        (out_dir / fname).write_text(content, encoding="utf-8")

        agg_parts.append(content)

        if r["status"] == "PASS":
            any_pass = True

        metrics_rows.append({
            "alias": r["alias"],
            "route": r["route"],
            "model": r.get("actual_model", r.get("model_cfg", "")),
            "status": r["status"],
            "error": r.get("error"),
            "latency_s": r["latency"],
            "est_cost_usd": r["est_cost"],
        })

    # ---- aggregate.md ----
    (out_dir / "aggregate.md").write_text("\n".join(agg_parts) + "\n", encoding="utf-8")

    # ---- metrics.json ----
    (out_dir / "metrics.json").write_text(json.dumps(metrics_rows, indent=2) + "\n",
                                          encoding="utf-8")

    # ---- stdout table ----
    print(f"{'ALIAS':20} {'STATUS':8} {'LATENCY':>8} {'EST COST':>10}")
    print("-" * 50)
    for r in results:
        status = r["status"]
        cost_str = f"${r['est_cost']:.6f}" if r["est_cost"] else "-"
        print(f"{r['alias']:20} {status:8} {r['latency']:7.1f}s {cost_str:>10}")
    print(f"\noutput: {out_dir}")

    sys.exit(0 if any_pass else 1)


if __name__ == "__main__":
    main()