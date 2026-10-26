# Soupop data workspace

Open this folder in Codex to ask data questions and build Metabase questions and dashboards at `https://mt.soupop.ir`. Codex reads `AGENTS.md`, the skills in `.agents/skills/` and the business rules in `business-logic/`, so you can ask in plain words.

## First-time setup (about 10 minutes)

1. Install the Codex app (or the Codex CLI) and sign in to your OpenAI account.
2. Get this folder: `git clone <repo url>`, or download it as a zip from GitHub.
3. In a terminal, from this folder, run:
   ```bash
   python3 tools/check_setup.py
   ```
   It checks the network, Metabase, which connection mode to use, your sign-in and Codex, and tells you how to fix anything marked `FIX`.
4. Sign in to Metabase with your own account, as the check tells you:
   - **API mode:** `python3 tools/metabase_agent.py login` (your Metabase email and password; only a session token is saved, in `.env`).
   - **MCP mode:** copy `codex/config.toml.example` into `~/.codex/config.toml`, then run `codex mcp login metabase`.
5. Open this folder in Codex and try a card from [prompts/prompt-cards.md](prompts/prompt-cards.md).

Run `git pull` now and then to get updated rules and skills.

## What's here

| Path | What it is |
|---|---|
| `AGENTS.md` | Instructions Codex follows in this folder |
| `.agents/skills/` | `soupop-rules`, `metabase-question`, `metabase-dashboard` |
| `business-logic/` | Table meanings, metric definitions and dashboard links |
| `prompts/prompt-cards.md` | Ready-made prompts |
| `tools/check_setup.py` | Setup checklist; writes `.workspace-state.json` |
| `tools/metabase_agent.py` | Metabase API helper (API mode) |
| `tools/fetch_schema.py` | Saves a schema snapshot to `schema/` as a fallback |
| `workspace.config.json` | Metabase address, VPN switch, staff collection |
| `codex/config.toml.example` | Codex MCP entry for Metabase 62+ |

## For maintainers

- **VPN:** set `requires_vpn` to `true` in `workspace.config.json` when Metabase moves behind the org VPN; the check then probes `vpn_probe_url` first. `SOUPOP_REQUIRES_VPN=1` or `0` overrides it for one run.
- **Staff collection:** set `staff_collection_id` once the `Staff` collection exists in Metabase.
- **Secrets:** `.env`, `.workspace-state.json` and `schema/` are git-ignored. Never commit them.
- Analyst material (credit research, cash-flow workbook, dashboard builder scripts, the SQL dump) stays out of this repo.
