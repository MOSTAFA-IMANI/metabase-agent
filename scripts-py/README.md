# Python scripts

Run every script from the workspace root, for example `python3 scripts-py/check_setup.py`. All of them use the standard library only and read credentials from `.env` in the workspace root through `metabase_agent.py`.

| Script | What it does |
|---|---|
| `check_setup.py` | Setup check Codex runs; writes `.workspace-state.json` (staff) |
| `metabase_agent.py` | Metabase REST API client and command-line helper (`login`, `sql`, `search`, ...) |
| `fetch_schema.py` | Saves a schema snapshot to `sql/snapshot/` |
| `schema_browser.py` | Browses tables and columns in `sql/soupop.sql` |
| `build_soupop_structure.py` | Builds the numbered `soupop-metabase` collections and dashboards |
| `build_*.py` | Analyst builders for saved questions and dashboards. Most create a **new** dashboard every run; read the existing one first. |
| `add_ai_chatbot_source_analytics.py` | Idempotent updater for dashboard 37 |
| `fetch_cashflow_data.py` | Reads cash-flow inputs into `data/soupop_cashflow_source.json` for `scripts-js/build_cashflow_projection.mjs` |

`business-logic/Analytics/README.md` maps each builder to the dashboard or question it made.
