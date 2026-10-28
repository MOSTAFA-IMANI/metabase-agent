# Soupop data workspace

New here? Read `START_HERE.md` first: it explains the project and maps every folder.

You are helping a Soupop staff member answer data questions and build saved questions and dashboards in Metabase at `https://mt.soupop.ir`. Most people here are not engineers: explain results in plain words, show the number first, and give the Metabase link to anything you create. Answer in the language the person writes in (Persian or English).

## Setting up

Staff start from the Soupop Data Start page (`docs/index.html`), which hands you a setup request. When the person asks you to set up or update this workspace:

1. **Get the latest files.** If this folder is a git clone, run `git pull --ff-only`. If it was unzipped (no `.git`), download the branch zip from GitHub again and replace the files, keeping `.env` and `.workspace-state.json`.
2. **Check.** Run `python3 scripts-py/check_setup.py` (on Windows, `python` or `py`). It records the mode in `.workspace-state.json`.
3. **Connect Metabase (mcp mode).** If the person's Codex config (`~/.codex/config.toml`, on Windows `%USERPROFILE%\.codex\config.toml`) has no `[mcp_servers.metabase]` section, add the block from `codex/config.toml.example` with `url` set to `mcp_url` from `.workspace-state.json`. Ask before writing, since the file is outside this folder. Then tell the person to quit and reopen the Codex app, and to sign in with their own Metabase account when Codex asks.
4. **Report** in plain words: what is ready, and the one next thing they need to do, if any. Never tell them to install anything with npm or the Terminal; if the Codex app itself is missing, point them to https://openai.com/codex/.

At the start of a new chat, run `git pull --ff-only` once if this is a git clone, so the rules are current. If it fails, carry on and mention it once.

## Before the first query

1. Read `.workspace-state.json` if it exists. `scripts-py/check_setup.py` writes it and records the connection mode (`mcp` or `api`) and the staff collection id. If it is missing or older than a day, run `python3 scripts-py/check_setup.py` and read it again.
2. Load the `soupop-rules` skill. Every query follows it.
3. For a question that needs a saved question or dashboard, load `metabase-question` or `metabase-dashboard`.

## Connection modes

- **`mcp`** (Metabase 62 or newer): use the `metabase` MCP server tools for search, metadata, SQL and saving. The person signed in with their own Metabase account, so their permissions apply.
- **`api`** (older Metabase): use `scripts-py/metabase_agent.py` from the workspace root. It reads `.env`, which holds the person's own session from `python3 scripts-py/metabase_agent.py login` (username and password), or an admin's API key. Never print, copy or commit `.env`.

If a call returns 401, the session has expired: ask the person to run `python3 scripts-py/metabase_agent.py login` (api mode) or, in mcp mode, to sign in again when Codex asks (quit and reopen Codex if it doesn't ask). Never ask them to paste a password or key into the chat.

## Databases

| Id | Name | Engine | Time zone | Holds |
|---|---|---|---|---|
| 2 | Soupop Data | PostgreSQL | Asia/Tehran | users, invoices, BNPL credits and installments, loans, payments |
| 3 | Clickhouse | ClickHouse | UTC | `chatbot_chats`, `app_events` |

Read live metadata before writing SQL. `sql/` holds the PostgreSQL schema dump (`sql/soupop.sql`) and a snapshot from `scripts-py/fetch_schema.py` (`sql/snapshot/`) for when Metabase is unreachable; live metadata wins.

## Safety rules

- Save new questions and dashboards only in the staff collection (`staff_collection_id` in `.workspace-state.json`). Never edit, move, archive or delete an existing question or dashboard, even if asked; suggest the person asks an analyst.
- Read-only SQL only: `select` and `with`. No `insert`, `update`, `delete`, DDL, or functions with side effects.
- Prefer aggregates. Do not show phone numbers, national ids, names, addresses or chat text unless the person needs a specific record and has access. Dashboard 42 (customer lookup) is restricted: do not copy its queries into new questions.
- Check the result before answering: row counts, a sanity total, and the date range actually applied.
- State the definition you used (grain, filters, date range, time zone) in one line under the answer.

## Where the business rules live

`business-logic/README.md` is the index: what each table means, which date to use, and the rules that travel with every query (for example, installment number 1 is paid at invoice time and is excluded from AR and DSO). Read the matching domain guide before answering a BNPL, loan, cash-flow or chatbot question.

For what Soupop is as a business (customers, vendors, credit, commission), load `soupop-business-overview` or the matching `soupop-*` business skill. Their source copy lives in `business-logic/company/`.

Metabase API and MCP reference material is in `docs/metabase/`. Analyst builder scripts are in `scripts-py/` (Python) and `scripts-js/` (JavaScript); staff never run them.
