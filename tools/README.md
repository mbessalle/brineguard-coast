# tools/

Reusable scripts, not one-off throwaways. Add to this directory (and document here)
whenever a script gets written a second time — that's the signal it should live here
instead of being reinvented per-task.

## gemini_deep_research.py

Runs a query through Gemini's Deep Research agent (multi-step autonomous web research,
own search/planning loop) via the async Interactions API and saves the final report.

```bash
GEMINI_API_KEY=$(cat .env.gemini_key) python3 tools/gemini_deep_research.py \
  "your research query" -o out.md
```

Takes several minutes (polls every 15s by default). Note: this is a *separate* API
surface from normal chat models — it does not support custom function-calling/tools,
only built-in Google Search / URL Context / Code Execution. It cannot be used as a
coding-agent backend (e.g. as pi's model) for that reason.

## gemini_flash.py

Plain single-turn call to a fast Gemini model (default `gemini-3.7-flash`) via the
standard `generateContent` API. Use for quick reviews/summaries, not multi-step agentic
work.

```bash
GEMINI_API_KEY=$(cat .env.gemini_key) python3 tools/gemini_flash.py "your prompt"
```

## Key file

## model_freshness.py

Zero-token model-drift detector — diffs pinned SSSF routes against the live
OpenRouter catalog and the local codex models cache. Run at every session start
(via `session_brief.sh`). Exit 0 always (informational).

```bash
python3 tools/model_freshness.py                # human-readable report
python3 tools/model_freshness.py --json         # machine-readable
python3 tools/model_freshness.py --config /tmp/cfg.yaml  # test with doctored config
```

Output: one "DRIFT …" line per stale route + summary; or "all pinned routes current".

## Key file

`.env.gemini_key` (gitignored) holds the raw Gemini API key, one line, no quotes.
Never commit it or print it to a shared/logged terminal.

## openrouter_call.py

OpenRouter access for SSSF Workhorse roles. Key from `OPENROUTER_API_KEY` or gitignored
`.env` (`OPENROUTER_API_KEY=...`); never printed.

```bash
python3 tools/openrouter_call.py models deepseek kimi     # live catalog + pricing
python3 tools/openrouter_call.py chat -m deepseek/deepseek-v4-pro "prompt" [-o out.md]
```

## probe.py

Uniform backend prober — one sentinel prompt through every model route (claude, codex,
pi×openrouter, pi×google, openrouter direct, gemini). Backends are template-table rows:
adding/altering a route is a one-line edit, not new code. Exit 0 = all pass.

```bash
python3 tools/probe.py                                    # probe everything
python3 tools/probe.py pi --model moonshotai/kimi-k3      # one route, model override
```

## fanout.py

Concurrent read-only multi-route fan-out engine for /fh-opinion and /fh-debate skills.
Resolves every requested route to a chat-only OpenRouter API call (no agentic paths);
routes on session/codex-cli backends are skipped. Output is anonymized — saved files
use alias labels only, never real model names.

```bash
python3 tools/fanout.py --prompt "Tell me about Python"       # fanned to default routes
python3 tools/fanout.py --prompt-file question.md --routes scout,builder
python3 tools/fanout.py --prompt "x" --dry-run                # inspect planned calls
```

## session_brief.sh

Deterministic session-start orientation (git state, memory index, docs, agent CLI +
Orca presences, standing orders). Run automatically by the SessionStart hook in
`.claude/settings.json`; callable manually any time.

## fetch_gebco.py

Download a GEBCO bathymetry subset for a bounding box as netCDF via a public
ERDDAP server (no auth). Saves under `data/registry/gebco/` with a provenance JSON
sidecar (sha256, bbox, retrieval time, license).

```bash
python3 tools/fetch_gebco.py                                    # default Red Sea corridor
python3 tools/fetch_gebco.py --bbox 26 29 34 37 -o my_bathy.nc
python3 tools/fetch_gebco.py --url-template "https://HOST/erddap/griddap/DS.nc?elevation[({lat_min}):1:({lat_max})][({lon_min}):1:({lon_max})]"
```

Default ERDDAP endpoint: IFREMER (gebco2021). Override with `--url-template` to
point at a different server or a newer GEBCO release (e.g. GEBCO 2025 when available).
Sanity-prints elevation min/max after download; Red Sea depths should reach below
−1000 m.

## fetch_cmems.py

Copernicus Marine currents fetcher. Requires the `copernicusmarine` Python package
and valid credentials (env vars or `~/.copernicusmarine` config). When either is
missing the script prints precise setup instructions and exits with code 2 — this
is the expected outcome until credentials are provisioned.

```bash
python3 tools/fetch_cmems.py --dataset-id <ID> --bbox 26 29 34 37 --start 2024-01-01 --end 2024-01-02
```

Find Red Sea product IDs at https://data.marine.copernicus.eu (filter by region =
"Red Sea", variable = "sea_water_velocity"). On success saves under
`data/registry/cmems/` with a provenance JSON sidecar.
- agent_io_log.sh — register every agent call (prompt/stdout/meta) to the agent-io branch for debugging
