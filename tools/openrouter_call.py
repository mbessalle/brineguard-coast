#!/usr/bin/env python3
"""OpenRouter caller for SSSF Workhorse-tier single-turn roles and model discovery.

Reads the API key from $OPENROUTER_API_KEY, else from a key file (.env with
OPENROUTER_API_KEY=..., or a raw single-line key). The key never touches argv,
stdout, or logs.

Usage:
  python3 tools/openrouter_call.py models [substring ...]   # list live model ids
  python3 tools/openrouter_call.py chat -m <model_id> "prompt"  [-s system] [-o out.md]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

BASE = "https://openrouter.ai/api/v1"
KEY_FILES = (".env", ".env.openrouter_key")


def load_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if key:
        return key
    for name in KEY_FILES:
        try:
            text = open(name, encoding="utf-8").read()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("OPENROUTER_API_KEY"):
                return line.split("=", 1)[1].strip().strip("'\"")
        if name != ".env" and text.strip() and "=" not in text:
            return text.strip()
    sys.exit("No OpenRouter key: set OPENROUTER_API_KEY or put OPENROUTER_API_KEY=... in .env")


def request(path: str, payload: dict | None = None, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode() if payload else None,
        headers={"Authorization": f"Bearer {load_key()}", "Content-Type": "application/json"},
    )
    # timeout is socket-silence, and non-streaming chat sends nothing until done —
    # so this must be >= the longest expected model thinking time (caller decides)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    models = sub.add_parser("models")
    models.add_argument("filters", nargs="*")
    chat = sub.add_parser("chat")
    chat.add_argument("prompt")
    chat.add_argument("-m", "--model", required=True)
    chat.add_argument("-s", "--system")
    chat.add_argument("-o", "--out")
    args = parser.parse_args()

    if args.command == "models":
        rows = request("/models")["data"]
        for row in sorted(rows, key=lambda r: r["id"]):
            if not args.filters or any(f.lower() in row["id"].lower() for f in args.filters):
                pricing = row.get("pricing", {})
                print(f"{row['id']:55} in={pricing.get('prompt', '?')} out={pricing.get('completion', '?')}")
    else:
        messages = ([{"role": "system", "content": args.system}] if args.system else [])
        messages.append({"role": "user", "content": args.prompt})
        result = request("/chat/completions", {"model": args.model, "messages": messages})
        text = result["choices"][0]["message"]["content"]
        if args.out:
            open(args.out, "w", encoding="utf-8").write(text)
            print(f"wrote {len(text)} chars to {args.out} (model={result.get('model')})")
        else:
            print(text)


if __name__ == "__main__":
    main()
