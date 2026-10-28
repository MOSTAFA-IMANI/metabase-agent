# Soupop data workspace

Open this folder in the Codex app to ask data questions and build Metabase questions and dashboards at `https://mt.soupop.ir`. Codex reads `AGENTS.md`, the skills in `.agents/skills/` and the business rules in `business-logic/`, so you can ask in plain words. Agents and new maintainers: start with [`START_HERE.md`](START_HERE.md).

## Start here (Mac or Windows)

You need about 15 minutes, once.

**1. Download the project**

1. Click this link: [Download the Soupop data project (zip)](https://github.com/MOSTAFA-IMANI/metabase-agent/archive/refs/heads/main.zip).
2. Open your **Downloads** folder and double-click the zip file to unzip it. (On Windows: right-click it, choose **Extract All**, then **Extract**.)
3. Move the unzipped folder somewhere easy to find, for example **Documents**. You can rename it to `soupop-data`.

**2. Open the start page**

1. Open the folder, then the **docs** folder inside it.
2. Double-click **index.html**. It opens in your web browser. Chrome or Edge work best, because they can save your Metabase sign-in into the folder for you.

**3. Follow the page**

The page takes you through the rest, top to bottom:

1. Install the Codex app.
2. Check that Metabase answers (if it doesn't, turn on the VPN).
3. Install Node.js.
4. Add this folder to Codex as a project.
5. Connect to Metabase with your Metabase email and password, or an API key from an admin. The page saves it in this folder and shows whether the connection works and whether you can run SQL.

After that, pick an example on the page or type what you need, click **Copy for Codex**, and paste it into Codex.

## What a web page can't do, and how the start page handles it

| Step | Why a web page can't | What happens instead |
|---|---|---|
| See whether Codex or Node.js is installed | Browsers can't see installed apps or run commands | The page links the download and shows how to check; you tick **Done**, and it remembers |
| Open Codex | Browsers can't start apps | You switch to Codex; your request is already copied |
| Save your Metabase sign-in | Browsers can write files only in Chrome and Edge, into a folder you choose | Chrome and Edge save `.env` in this folder; other browsers download `soupop-metabase.env` for you to move into it |
| Test the sign-in and SQL access | Metabase answers other websites only if an admin allows them | If Metabase allows it, the page checks directly. Otherwise it copies a check request for Codex, and the page shows Codex's result |
| Update the project | Browsers can't replace your files | The page shows when the rules last changed and links the latest zip |

## What's here

[`START_HERE.md`](START_HERE.md) has the full folder map and a short system prompt for agents.

| Path | What it is |
|---|---|
| `START_HERE.md` | What the project is, folder map, short system prompt |
| `docs/index.html` | Soupop Data Start page (double-click it) |
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

- **VPN:** the start page passes the VPN step whenever Metabase answers. Set `requires_vpn` to `true` in `workspace.config.json` when Metabase moves behind the org VPN, so `check_setup.py` probes `vpn_probe_url` first; `SOUPOP_REQUIRES_VPN=1` or `0` overrides it for one run.
- **Let the page test sign-ins itself (optional):** Metabase only answers pages it trusts. Opened from a file, the page has no web address Metabase can trust, so Codex does the test. If the page is ever hosted (for example on GitHub Pages), an admin can add that address in Metabase's CORS setting, and the page then checks directly.
- **Branch:** the download link and the start page use `main`.
- **Staff collection:** set `staff_collection_id` once the `Staff` collection exists in Metabase.
- **Secrets:** `.env`, `soupop-metabase.env`, `.workspace-state.json`, `sql/snapshot/`, `data/` and `reports/` are git-ignored. Never commit them.
- **Paths the start page reads from GitHub:** `workspace.config.json`, `prompts/prompt-cards.md` and `business-logic/`. Keep them where they are.
- **Business skills:** edit them in `business-logic/company/skills/`, then copy to `.agents/skills/` (see `business-logic/company/README.md`).
