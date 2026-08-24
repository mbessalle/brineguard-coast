#!/usr/bin/env python3
"""Call a Gemini flash model (default: gemini-3.7-flash) via the standard generateContent API.

Plain synchronous request/response - use this for fast/cheap Google-model turns
(e.g. quick reviews, summarization) as opposed to gemini_deep_research.py, which is
for long-running autonomous multi-step research.

Usage:
    GEMINI_API_KEY=... python3 gemini_flash.py "<prompt>" [-o out.md] [--model gemini-3.7-flash]
    echo "<prompt>" | python3 gemini_flash.py -
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def generate(prompt: str, api_key: str, model: str = "gemini-3.7-flash") -> str:
    url = f"{BASE}/{model}:generateContent"
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    req = urllib.request.Request(
        url, data=json.dumps(body).encode(), method="POST",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e

    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"No candidates in response: {json.dumps(data)[:1000]}")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "\n".join(p["text"] for p in parts if "text" in p)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("prompt", help="Prompt text, or '-' to read from stdin")
    p.add_argument("-o", "--output", help="File to write the result to (default: stdout)")
    p.add_argument("--model", default="gemini-3.7-flash")
    p.add_argument("--key-file", help="Path to a file containing the API key (alternative to $GEMINI_API_KEY)")
    args = p.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and args.key_file:
        api_key = open(args.key_file).read().strip()
    if not api_key:
        print("error: set GEMINI_API_KEY or pass --key-file", file=sys.stderr)
        return 1

    prompt = sys.stdin.read() if args.prompt == "-" else args.prompt

    try:
        text = generate(prompt, api_key, model=args.model)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if args.output:
        with open(args.output, "w") as f:
            f.write(text)
        print(f"wrote {len(text)} chars to {args.output}", file=sys.stderr)
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
