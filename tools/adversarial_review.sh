#!/usr/bin/env bash
# THE adversarial review command (audit X13/X21/X10): one wrapper that
# enforces the model, effort, timeout, read-only sandbox, and ledger logging
# that the prose recipes promised but did not implement. Use this, not raw
# codex/pi invocations, for any review that will justify a FINAL/agreed label.
#
# Usage: bash tools/adversarial_review.sh <tag> <prompt-file> [timeout-s]
# Exit:  0 review completed (findings on stdout + ledger), 124 timeout, else codex error.
set -euo pipefail
tag=${1:?tag}; promptf=${2:?prompt-file}; budget=${3:-560}
MODEL=gpt-5.6-sol
outf=$(mktemp) ; errf=$(mktemp)
trap 'rm -f "$outf" "$errf"' EXIT

set +e
timeout "$budget" codex exec --sandbox read-only -m "$MODEL" \
  -c model_reasoning_effort='"high"' "$(cat "$promptf")" <"/dev/null" >"$outf" 2>"$errf"
ec=$?
set -e
# codex can exit 0 while streaming a structured error (verified live)
if grep -q '"type":"error"' "$outf"; then ec=1; fi

bash "$(dirname "$0")/agent_io_log.sh" "$tag" "$promptf" "$outf" "$errf" "$ec" "$MODEL" \
  "adversarial_review.sh effort=high sandbox=read-only budget=${budget}s" >&2

cat "$outf"
exit "$ec"
