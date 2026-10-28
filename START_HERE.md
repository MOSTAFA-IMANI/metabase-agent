# Start here

Read this first if you are an AI agent (Codex, Claude or another) or a person opening this folder for the first time.

## What this project is

Soupop is an automotive fintech platform: car owners get BNPL credit or a loan through Soupop, spend it at contracted service vendors, and Soupop earns a commission from the vendor. The company's data lives in Metabase at `https://mt.soupop.ir`:

- Database 2, **Soupop Data** (PostgreSQL, Asia/Tehran time): users, invoices, BNPL credits and installments, loans, payments.
- Database 3, **Clickhouse** (ClickHouse, UTC): `chatbot_chats`, `app_events`.

This workspace lets Soupop staff ask data questions in plain words (Persian or English) and get correct numbers, saved questions and dashboards in Metabase. It holds the agent instructions, the business rules every query must follow, the database schema, the Metabase API and MCP docs, and the scripts analysts use to build dashboards.

## Short system prompt

Use this when an agent tool asks for instructions, or paste it at the top of a chat:

```text
You are the Soupop data assistant. You help Soupop staff answer data questions and build
saved questions and dashboards in Metabase at https://mt.soupop.ir. Most people are not
engineers: answer in the language they write in, give the number first in plain words,
then one line with the definition you used (grain, filters, date range, time zone), and
the Metabase link to anything you create.

Before any query, follow AGENTS.md and the soupop-rules skill. Read live Metabase metadata
before writing SQL. Run read-only SQL only (select / with). Save new questions and
dashboards only in the staff collection, and never edit, move or delete existing ones.
Prefer aggregates and do not show personal data (phone numbers, national ids, names,
addresses, chat text). Never print, copy or commit .env, API keys or passwords.
Check every result (row count, a sanity total, the date range applied) before answering.
```

## Read in this order

1. `AGENTS.md`: setup, connection modes (MCP or API), safety rules.
2. `.agents/skills/soupop-rules/SKILL.md`: the query rules every answer follows.
3. `business-logic/README.md`: what each table means and which date to use, then the matching domain guide.
4. For a saved question or dashboard: `.agents/skills/metabase-question/` or `.agents/skills/metabase-dashboard/`.
5. For business context (customers, vendors, commission): the `soupop-business-overview` skill and `business-logic/company/`.

## Folder map

```text
.
├── START_HERE.md            this file: what the project is, folder map, system prompt
├── AGENTS.md                instructions Codex follows in this folder (setup, safety)
├── README.md                human guide: how staff start, what's where
├── workspace.config.json    Metabase address, VPN switch, staff collection (the start page reads it)
├── .agents/skills/          skills the agent loads
│   ├── soupop-rules/            query rules (always)
│   ├── metabase-question/       how to build a saved question
│   ├── metabase-dashboard/      how to build a dashboard
│   └── soupop-*/                five business skills: overview, customer demand,
│                                vendor supply, transactions and revenue, growth and metrics
├── business-logic/          business rules and definitions
│   ├── README.md                index: tables, dates, rules, live dashboard links
│   ├── BNPL/  Loan/             schema notes and workflow stories per product
│   ├── Analytics/               AR/DSO, cash-flow and chatbot methods, dashboard map
│   ├── Credit/                  credit research and new-user credit backend rules
│   └── company/                 business model overview (Persian) and the source copy
│                                of the Soupop business skills
├── sql/                     database schema
│   ├── soupop.sql               PostgreSQL schema dump (tables and indexes, no data)
│   └── snapshot/                live snapshot from scripts-py/fetch_schema.py (git-ignored)
├── docs/
│   ├── index.html               Soupop Data Start page (double-click it)
│   └── metabase/                how to call the Metabase API and connect by MCP
├── scripts-py/              all Python: setup check, Metabase client, dashboard builders
├── scripts-js/              JavaScript: cash-flow workbook builder
├── scripts-sh/              shell: Mac helper that saves an API key to .env
├── codex/                   Codex config example for the Metabase MCP server
├── prompts/                 ready-made prompts the start page shows
├── data/                    local script inputs and outputs (git-ignored)
└── reports/                 generated workbooks and exports (git-ignored)
```

## Rules that never change

- Secrets stay in `.env` at the workspace root. It is git-ignored; never print, paste or commit it.
- Live Metabase metadata beats `sql/soupop.sql`, which is a point-in-time dump.
- Most `scripts-py/build_*.py` scripts create a new dashboard every run. Read the existing dashboard and the script before running one; they are for analysts, not staff.
- Run scripts from the workspace root, for example `python3 scripts-py/check_setup.py`.
