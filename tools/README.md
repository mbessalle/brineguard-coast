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
