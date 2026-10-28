# Soupop data workspace

Open this folder in the Codex app to ask data questions and build Metabase questions and dashboards at `https://mt.soupop.ir`. Codex reads `AGENTS.md`, the skills in `.agents/skills/` and the business rules in `business-logic/`, so you can ask in plain words. Agents and new maintainers: start with [`START_HERE.md`](START_HERE.md).

## Start here (Mac or Windows)

Open the **Soupop Data Start** page and follow it:

- Online: `https://mostafa-imani.github.io/metabase-agent/` (after GitHub Pages is turned on, see below).
- Offline copy: download [`docs/index.html`](docs/index.html) and double-click it.

The page checks the VPN (only when needed) and Metabase, shows when the rules and business docs last changed, links the Codex app download, and gives you a setup request to paste into Codex. Codex then downloads this workspace into a folder, connects Metabase and checks everything. After that, pick an example or type what you need, click **Copy for Codex**, and paste it into Codex.

## What a web page can't do, and who does it instead

| Step | Why the page can't | Who does it |
|---|---|---|
| Is the Codex app installed? | Browsers can't see installed apps | You tick **Done** after installing; the tick is remembered |
| Open Codex | Browsers can't start apps | You switch to Codex; the request is already copied |
| Download and update the workspace | Browsers can't write to your folders | Codex, from the setup request, and `git pull` at the start of each chat |
| Connect Codex to Metabase | Browsers can't edit Codex settings | Codex, during setup (asks first) |
| Metabase version and sign-in | Metabase doesn't share its answers with other websites | Codex runs `scripts-py/check_setup.py`; Codex asks you to sign in |

## What's here

[`START_HERE.md`](START_HERE.md) has the full folder map and a short system prompt for agents.

| Path | What it is |
|---|---|
| `START_HERE.md` | What the project is, folder map, short system prompt |
| `docs/index.html` | Soupop Data Start page |
| `AGENTS.md` | Instructions Codex follows in this folder, including setup |
| `.agents/skills/` | `soupop-rules`, `metabase-question`, `metabase-dashboard` and five Soupop business skills |
| `business-logic/` | Table meanings, metric definitions, credit research, business model and dashboard links |
| `sql/` | PostgreSQL schema dump and the live schema snapshot |
| `docs/metabase/` | Metabase API reference, API key setup, API runbook and MCP setup |
| `scripts-py/` | Python: setup check, Metabase API helper, schema tools, dashboard builders |
| `scripts-js/` | JavaScript: cash-flow workbook builder |
| `scripts-sh/` | Shell: Mac API-key helper |
| `prompts/prompt-cards.md` | Ready-made prompts; the start page shows them |
| `workspace.config.json` | Metabase address, VPN switch, staff collection |
| `codex/config.toml.example` | Codex MCP entry for Metabase 62+ |
| `data/`, `reports/` | Script outputs and generated workbooks (git-ignored) |

## For maintainers

- **Publish the start page:** on GitHub, open **Settings > Pages**, set **Source** to "Deploy from a branch", pick the branch and the `/docs` folder, and save.
- **VPN:** set `requires_vpn` to `true` in `workspace.config.json` when Metabase moves behind the org VPN. The start page reads it from GitHub on every load and probes `vpn_probe_url`; staff can override it on their own computer. `SOUPOP_REQUIRES_VPN=1` or `0` overrides it for one `check_setup.py` run.
- **Branch:** the start page uses `claude/workspace-v0` if it exists, otherwise `main`.
- **Staff collection:** set `staff_collection_id` once the `Staff` collection exists in Metabase.
- **Secrets:** `.env`, `.workspace-state.json`, `sql/snapshot/`, `data/` and `reports/` are git-ignored. Never commit them.
- **Paths the start page reads from GitHub:** `workspace.config.json`, `prompts/prompt-cards.md` and `business-logic/`. Keep them where they are.
- **Business skills:** edit them in `business-logic/company/skills/`, then copy to `.agents/skills/` (see `business-logic/company/README.md`).
