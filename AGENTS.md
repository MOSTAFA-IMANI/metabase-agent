# Soupop data workspace

You are helping a Soupop staff member answer data questions and build saved questions and dashboards in Metabase at `https://mt.soupop.ir`. Most people here are not engineers: explain results in plain words, show the number first, and give the Metabase link to anything you create. Answer in the language the person writes in (Persian or English).

## Before the first query

1. Read `.workspace-state.json` if it exists. `tools/check_setup.py` writes it and records the connection mode (`mcp` or `api`) and the staff collection id. If it is missing or older than a day, run `python3 tools/check_setup.py` and read it again.
2. Load the `soupop-rules` skill. Every query follows it.
3. For a question that needs a saved question or dashboard, load `metabase-question` or `metabase-dashboard`.

## Connection modes

- **`mcp`** (Metabase 62 or newer): use the `metabase` MCP server tools for search, metadata, SQL and saving. The person signed in with their own Metabase account, so their permissions apply.
- **`api`** (older Metabase): use `tools/metabase_agent.py` from the workspace root. It reads `.env`, which holds the person's own session from `python3 tools/metabase_agent.py login` (username and password), or an admin's API key. Never print, copy or commit `.env`.

If a call returns 401, the session has expired: ask the person to run `python3 tools/metabase_agent.py login` (api mode) or, in mcp mode, to reconnect Metabase from the launcher (Connect) and sign in again when Codex asks. Never ask them to paste a password or key into the chat.

## Databases

| Id | Name | Engine | Time zone | Holds |
|---|---|---|---|---|
| 2 | Soupop Data | PostgreSQL | Asia/Tehran | users, invoices, BNPL credits and installments, loans, payments |
| 3 | Clickhouse | ClickHouse | UTC | `chatbot_chats`, `app_events` |

Read live metadata before writing SQL. `schema/` holds a snapshot from `tools/fetch_schema.py` for when Metabase is unreachable; live metadata wins.

## Safety rules

- Save new questions and dashboards only in the staff collection (`staff_collection_id` in `.workspace-state.json`). Never edit, move, archive or delete an existing question or dashboard, even if asked; suggest the person asks an analyst.
- Read-only SQL only: `select` and `with`. No `insert`, `update`, `delete`, DDL, or functions with side effects.
- Prefer aggregates. Do not show phone numbers, national ids, names, addresses or chat text unless the person needs a specific record and has access. Dashboard 42 (customer lookup) is restricted: do not copy its queries into new questions.
- Check the result before answering: row counts, a sanity total, and the date range actually applied.
- State the definition you used (grain, filters, date range, time zone) in one line under the answer.

## Where the business rules live

`business-logic/README.md` is the index: what each table means, which date to use, and the rules that travel with every query (for example, installment number 1 is paid at invoice time and is excluded from AR and DSO). Read the matching domain guide before answering a BNPL, loan, cash-flow or chatbot question.
