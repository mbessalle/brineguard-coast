#!/usr/bin/env python3
"""Run a Gemini Deep Research task via the async Interactions API and save the result.

Deep Research is not reachable through the normal generateContent/chat API - it lives
behind a separate asynchronous "Interactions" endpoint (create, then poll). This wraps
that flow so no one has to hand-roll the create+poll loop again.

Usage:
    GEMINI_API_KEY=... python3 gemini_deep_research.py "<research query>" -o out.md [--agent deep-research-preview-04-2026]

Reads the API key from $GEMINI_API_KEY (or --key-file). Never pass the key on the
command line where it could land in shell history / process listings.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://generativelanguage.googleapis.com/v1beta/interactions"


def _request(url: str, api_key: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("x-goog-api-key", api_key)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e


def run_deep_research(
    query: str,
    api_key: str,
    agent: str = "deep-research-preview-04-2026",
    poll_seconds: int = 15,
    timeout_seconds: int = 3600,
    on_progress=None,
) -> dict:
    """Create a Deep Research interaction and poll until it completes or fails.

    Returns the final interaction object. Raises RuntimeError on failure/timeout.
    """
    create_body = {
        "agent": agent,
        "input": query,
        "background": True,
        "agent_config": {
            "type": "deep-research",
            "thinking_summaries": "auto",
            "visualization": "auto",
            "collaborative_planning": False,
        },
        "tools": [{"type": "google_search"}],
    }
    created = _request(BASE, api_key, method="POST", body=create_body)
    interaction_id = created.get("name") or created.get("id")
    if not interaction_id:
        raise RuntimeError(f"No interaction id in create response: {created}")
    interaction_id = interaction_id.rsplit("/", 1)[-1]

    deadline = time.time() + timeout_seconds
    last_status = None
    while time.time() < deadline:
        state = _request(f"{BASE}/{interaction_id}", api_key)
        status = state.get("status")
        if status != last_status and on_progress:
            on_progress(status, state)
        last_status = status
        if status == "completed":
            return state
        if status == "failed":
            raise RuntimeError(f"Interaction failed: {json.dumps(state)[:2000]}")
        time.sleep(poll_seconds)
    raise RuntimeError(f"Timed out after {timeout_seconds}s waiting for interaction {interaction_id}")


def extract_text(state: dict) -> str:
    """Pull the final report text, skipping user_input echo and internal 'thought' steps.

    Verified against a real completed interaction: steps is a flat top-level list
    (user_input -> thought -> final content step), and only the last content-bearing
    step holds the actual report; 'thought' steps hold internal planning narration
    that should not be included in the saved output.
    """
    steps = state.get("steps") or state.get("interaction", {}).get("steps") or []
    report_steps = [s for s in steps if s.get("type") not in ("user_input", "thought")]
    target = report_steps[-1] if report_steps else (steps[-1] if steps else {})
    chunks = [c["text"] for c in target.get("content", []) if "text" in c]
    return "\n\n".join(chunks) if chunks else json.dumps(state, indent=2)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("query", help="The research query/prompt")
    p.add_argument("-o", "--output", required=True, help="File to write the result to")
    p.add_argument("--agent", default="deep-research-preview-04-2026",
                    help="deep-research-preview-04-2026 or deep-research-max-preview-04-2026")
    p.add_argument("--key-file", help="Path to a file containing the API key (alternative to $GEMINI_API_KEY)")
    p.add_argument("--poll-seconds", type=int, default=15)
    p.add_argument("--timeout-seconds", type=int, default=3600)
    args = p.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and args.key_file:
        api_key = open(args.key_file).read().strip()
    if not api_key:
        print("error: set GEMINI_API_KEY or pass --key-file", file=sys.stderr)
        return 1

    def on_progress(status, _state):
        print(f"[deep-research] status={status}", file=sys.stderr)

    try:
        final = run_deep_research(
            args.query, api_key, agent=args.agent,
            poll_seconds=args.poll_seconds, timeout_seconds=args.timeout_seconds,
            on_progress=on_progress,
        )
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    text = extract_text(final)
    with open(args.output, "w") as f:
        f.write(text)
    print(f"wrote {len(text)} chars to {args.output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
