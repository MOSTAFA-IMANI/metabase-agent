# Soupop data workspace

Open this folder in Codex to ask data questions and build Metabase questions and dashboards at `https://mt.soupop.ir`. Codex reads `AGENTS.md`, the skills in `.agents/skills/` and the business rules in `business-logic/`, so you can ask in plain words.

## Start the launcher (Mac)

1. Download [Soupop-Data-mac.zip](https://github.com/MOSTAFA-IMANI/metabase-agent/raw/claude/workspace-v0/download/Soupop-Data-mac.zip) and double-click it to unzip.
2. Drag **Soupop Data** into **Applications**.
3. Open it. The first time, macOS says it can't check the app: open **System Settings > Privacy & Security**, scroll down and click **Open Anyway** next to "Soupop Data". (On older macOS: right-click the app, choose **Open**, then **Open**.)

Soupop Data downloads this workspace into `~/soupop-data` the first time, updates it every time you open it, and shows the checklist page in your browser. Use **Quit launcher** on the page to stop it. If Apple's developer tools are missing, it asks you to install them once.

## Without the launcher

1. Install the Codex app for Mac from [openai.com/codex](https://openai.com/codex/) and sign in to your OpenAI account.
2. Run `python3 tools/check_setup.py` in this folder and fix anything marked `FIX`.
3. Sign in to Metabase with your own account:
   - **API mode:** `python3 tools/metabase_agent.py login` (only a session token is saved, in `.env`).
   - **MCP mode:** copy `codex/config.toml.example` into `~/.codex/config.toml`; the Codex app asks you to sign in to Metabase the first time.
4. Open this folder in Codex and try a card from [prompts/prompt-cards.md](prompts/prompt-cards.md).

## What's here

| Path | What it is |
|---|---|
| `AGENTS.md` | Instructions Codex follows in this folder |
| `.agents/skills/` | `soupop-rules`, `metabase-question`, `metabase-dashboard` |
| `business-logic/` | Table meanings, metric definitions and dashboard links |
| `prompts/prompt-cards.md` | Ready-made prompts |
| `start.command`, `launcher/` | Mac launcher: a local page on 127.0.0.1 that runs the checklist, signs in, updates, and opens Codex |
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
