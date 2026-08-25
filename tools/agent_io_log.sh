#!/usr/bin/env bash
# Register one agent call (prompt + output + metadata) into the agent-io git
# branch for later debugging. Zero tokens, append-only, never touches master.
#
# Ledger worktree: ../water-innovation-agent-io  (branch: agent-io)
# Layout per call: calls/<utc-ts>_<tag>/{meta.json,prompt.txt,stdout.txt,stderr.txt}
#
# Usage:
#   bash tools/agent_io_log.sh <tag> <prompt-file> <stdout-file> [stderr-file] [exit-code] [model] [extra-note]
# Example:
#   bash tools/agent_io_log.sh oplayer-audit p.txt out.txt err.txt 0 gpt-5.6-sol "thinking=medium"
set -euo pipefail
LEDGER="$(cd "$(dirname "$0")/.." && pwd)/../water-innovation-agent-io"
[ -d "$LEDGER/.git" ] || [ -f "$LEDGER/.git" ] || { echo "FATAL: ledger worktree missing at $LEDGER (git worktree add ../water-innovation-agent-io agent-io)" >&2; exit 1; }

tag=${1:?tag}; prompt=${2:?prompt-file}; out=${3:?stdout-file}
err=${4:-}; code=${5:-unknown}; model=${6:-unknown}; note=${7:-}

ts=$(date -u +%Y%m%dT%H%M%SZ)
dir="$LEDGER/calls/${ts}_${tag}"
mkdir -p "$dir"
cp -- "$prompt" "$dir/prompt.txt"
cp -- "$out" "$dir/stdout.txt" 2>/dev/null || echo "(stdout file missing: $out)" > "$dir/stdout.txt"
[ -n "$err" ] && cp -- "$err" "$dir/stderr.txt" 2>/dev/null || true
python3 - "$dir/meta.json" "$tag" "$code" "$model" "$note" "$prompt" "$out" <<'PYEOF'
import json, sys, os, datetime
meta = dict(tag=sys.argv[2], exit_code=sys.argv[3], model=sys.argv[4],
            note=sys.argv[5], prompt_src=os.path.abspath(sys.argv[6]),
            stdout_src=os.path.abspath(sys.argv[7]),
            registered_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            prompt_bytes=os.path.getsize(sys.argv[6]) if os.path.exists(sys.argv[6]) else None,
            stdout_bytes=os.path.getsize(sys.argv[7]) if os.path.exists(sys.argv[7]) else None)
json.dump(meta, open(sys.argv[1], "w"), indent=2)
PYEOF
# secret scan before anything is committed (audit X23); stage ONLY this call
if grep -rlE "sk-[A-Za-z0-9]{20}|OPENROUTER_API_KEY=[A-Za-z0-9]|BEGIN (RSA|OPENSSH) PRIVATE KEY" "$dir" >/dev/null 2>&1; then
  rm -rf "$dir"
  echo "FATAL: secret-like content detected; call NOT logged (redact and retry)" >&2
  exit 3
fi
git -C "$LEDGER" add "calls/${ts}_${tag}"
git -C "$LEDGER" commit -q -m "log: ${ts}_${tag} (model=$model exit=$code)"
echo "registered: calls/${ts}_${tag} on branch agent-io"
