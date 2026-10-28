# Soupop Metabase API runbook (analysts)

Use this guide for future questions, saved questions, and dashboards on `https://mt.soupop.ir`. It describes the working REST API connection as verified on 2026-10-05; for the MCP connection see [MCP.md](MCP.md). Check live metadata before relying on an ID or schema detail because Metabase and the databases can change.

## Start here

- Work from the workspace root: `scripts-py/metabase_agent.py` loads `.env` from there, and every command below is run from the root.
- Use [business-logic/README.md](../../business-logic/README.md) as the domain index for BNPL, loan operations, cash-flow, credit analysis, product analytics, and verified Metabase links.
- Use Python 3. The helper uses the standard library; there is no package-install step for basic API work.
- Read `scripts-py/metabase_agent.py` before changing API calls and inspect a relevant `scripts-py/build_*.py` or `scripts-py/add_*.py` script before changing a dashboard.
- Inspect the existing dashboard with `GET /api/dashboard/{id}` before modifying it. Preserve its cards, layout, tabs, filters, card mappings, and user edits.
- Do not run a `build_*.py` script merely to update an existing dashboard: many builders create a new dashboard and duplicate questions. Prefer an idempotent update script, such as `scripts-py/add_ai_chatbot_source_analytics.py`.

## Connection and credentials

`scripts-py/metabase_agent.py` reads `.env` in the workspace root. Expected names are:

```dotenv
METABASE_URL=https://mt.soupop.ir
METABASE_API_KEY=<secret API key>
METABASE_SESSION_ID=<secret login session; used by Agent API routes when required>
METABASE_DATABASE_ID=2
```

The current default database ID is `2`; set the database explicitly for a question about ClickHouse. `MetabaseClient.call` sends `X-API-Key` for the API key and `X-Metabase-Session` for the login session when present. Use the helper instead of assembling authorization headers manually. `.env` is git-ignored and should have permissions `0600`. Never print, paste into an agent prompt, commit, or send a real API key or session token in a response. Do not put a secret directly in a shell command where it can enter shell history or process listings. If a key has been exposed, ask the owner to rotate it.

To obtain an API key, an authorized Metabase admin can create one in Metabase's administration/API-key settings with a group that has the needed database and collection permissions. The raw key may only be shown when created; otherwise create a replacement. `python3 scripts-py/metabase_agent.py create-key --group-id <authorized_group_id> --database-id 2` prompts for the admin login and saves the result. For an existing key, `python3 scripts-py/metabase_agent.py save-key --api-key <key> --database-id 2` exists, but its argument can be exposed in shell history/process listings; use a secure local method and do not paste the value into a chat. Do not overwrite someone else's working `.env` just to switch databases.

Some `/api/agent/v1/*` calls require a login session even with an API key. Run `python3 scripts-py/metabase_agent.py login --database-id 2`; it prompts for credentials and saves `METABASE_SESSION_ID`. Repeat when the session expires. Standard Metabase routes such as `/api/card` and `/api/dashboard` work with the saved API key when its permissions allow them.

Quick connection checks:

```bash
python3 scripts-py/metabase_agent.py ping
python3 scripts-py/metabase_agent.py list-databases
python3 scripts-py/metabase_agent.py sql "select count(*) from users" --database-id 2
python3 scripts-py/metabase_agent.py sql "select count() from chatbot_chats" --database-id 3
```

`search database` searches Metabase assets, not the database inventory; use `list-databases` to find IDs.

## Known databases and tables

| Metabase database ID | Name | Engine | Typical work |
| --- | --- | --- | --- |
| `2` | `Soupop Data` | PostgreSQL | Operational users, orders, invoices, loans, credits, installments, maintenance |
| `3` | `Clickhouse` | ClickHouse | `chatbot_chats`, `app_events`, product analytics |

Known ClickHouse Metabase table IDs: `chatbot_chats` is `259`; `app_events` is `241`. In the 2026-10-05 metadata, `chatbot_chats.created_at` has field ID `2095` and `app_events.created_at` has field ID `1920`. Confirm IDs through live metadata before building field-filter questions.

Useful schema calls from Python (run from `scripts-py/`, or add it to `sys.path`):

```python
from metabase_agent import MetabaseClient

client = MetabaseClient()
databases = client.list_databases()
dashboard = client.call("GET", "/api/dashboard/37")
chat_fields = client.call("GET", "/api/table/259/query_metadata")
clickhouse_metadata = client.call("GET", "/api/database/3/metadata")
```

For PostgreSQL, inspect `information_schema.tables` and `information_schema.columns` in database 2. For ClickHouse, use `DESCRIBE TABLE chatbot_chats` or `DESCRIBE TABLE app_events` in database 3. Sample a few rows to understand JSON/map values before writing extraction SQL. `scripts-py/schema_browser.py` (reads `sql/soupop.sql`) can help with local schema discovery, but live Metabase metadata and live query results take precedence.

## Working API routes

Use `MetabaseClient` from `scripts-py/metabase_agent.py` so authentication and the base URL are consistent:

| Need | Route or helper |
| --- | --- |
| Test Agent API | `client.ping()` -> `GET /api/agent/v1/ping` |
| Run read-only SQL | `client.execute_sql(database_id, sql)` -> `POST /api/agent/v1/execute-sql` |
| List database IDs | `client.list_databases()` -> `GET /api/database` |
| Read dashboard | `client.call("GET", "/api/dashboard/<id>")` |
| Save native SQL question | `client.create_native_card(...)` -> `POST /api/card` |
| Run saved question | `client.call("POST", "/api/card/<id>/query", {"parameters": []})` |
| Create standard dashboard | `client.create_standard_dashboard(...)` -> `POST /api/dashboard` |
| Update dashboard cards | `client.update_standard_dashboard_cards(id, dashcards)` -> `PUT /api/dashboard/<id>` |

Do not assume `POST /api/agent/v1/construct-native-query` or `PUT /api/agent/v1/dashboard/{id}` exists on this instance: both previously returned 404. For a saved SQL question, use `POST /api/card` through `create_native_card`. For updating cards, use the standard dashboard route. A 401 from an Agent API call can mean the session is missing/expired; check permissions and re-login without revealing credentials.

## Question-to-dashboard workflow

1. Confirm the target database and inspect the live schema, relevant joins, timestamp timezone, and sample values. For maps such as ClickHouse `extra` or `params`, inspect available keys first. `raw_response` and some `extra` values are JSON-formatted strings; parse them with ClickHouse JSON functions, not text splitting.
2. Define the metric precisely: row grain, exclusions, distinct-user definition, date boundary, and whether the chart is a total or a daily series. For example, daily distinct users cannot be summed across days to get period distinct users.
3. Run a small read-only SQL validation with `client.execute_sql(db_id, sql)`. Compare against independent counts where possible. Avoid displaying raw personal data unless needed for the task.
4. Save a descriptively named question with `client.create_native_card(database_id, name, sql, display, description, template_tags=...)`. `display` is commonly `table`, `bar`, `line`, or `scalar`. Include a useful description of the metric and any limitations.
5. Execute the saved card via `/api/card/{id}/query`, first without filters and then with a realistic filter value. Check `status`, row count, sample rows, and the compiled query if results look unchanged.
6. Read the destination dashboard fresh. Add new dashcards without dropping or moving existing cards unless requested. Use valid `row`, `col`, `size_x`, and `size_y` values, and connect each applicable dashboard filter. Avoid creating the same named card twice; make update scripts idempotent.
7. Read the dashboard again to verify card IDs, positions, filter mappings, and original cards. Provide the actual `/dashboard/{id}` link, not an assumed URL. State any metric caveats.

Minimal Python pattern for a new native question:

```python
from metabase_agent import MetabaseClient

client = MetabaseClient()
database_id = 3  # Set explicitly; .env currently defaults to database 2.
sql = "select toDate(created_at) as day, count() as chats from chatbot_chats group by day order by day"
print(client.execute_sql(database_id, sql)["data"]["rows"][:5])
card = client.create_native_card(
    database_id=database_id,
    name="AI Chatbot - Daily Chats",
    sql=sql,
    display="line",
    description="Daily count of saved chatbot messages.",
)
print(f"{client.base_url}/question/{card['id']}")
```

For an existing dashboard, `GET /api/dashboard/{id}` returns `dashcards`. Preserve each card's `id`, `card_id`, position, size, `parameter_mappings`, `series`, `visualization_settings`, and any tab-related properties when sending the updated `dashcards` list. `scripts-py/add_ai_chatbot_source_analytics.py` is a working example for dashboard 37. Do not replace that dashboard with the older `scripts-py/build_ai_chatbot_analytics_dashboard.py` script.

## Dashboard filters: important Metabase detail

Native SQL with optional variables can use `[[and user_id = {{user_id}}]]`. The template tag type is `number`, and its dashboard mapping target is `["variable", ["template-tag", "user_id"]]`.

For a real date-range filter, use a **field filter**, not a plain text/date variable:

```sql
select count() as chats
from chatbot_chats
where 1 = 1
  [[and {{date_range}}]]
```

The card's `date_range` template tag must be a `dimension` tied to the live `created_at` field ID, for example:

```python
{"id": "date_range", "name": "date_range", "display-name": "Date range",
 "type": "dimension", "dimension": ["field", 2095, None],
 "widget-type": "date/all-options"}
```

The dashboard's `date/range` parameter must map to `["dimension", ["template-tag", "date_range"]]`. Mapping this field filter with `"variable"` can silently leave it unapplied, returning all-time counts. This was tested on dashboard 37. For `app_events`, use its own `created_at` field ID `1920`; the chat field ID must not be reused on event cards. Test with a bounded range and verify counts change. The same dashboard can map only relevant filters to each card: chat cards can use `session_id`/`llm_model`; event cards can use `params['type']`/`params['action']`.

## ClickHouse chatbot/event analytics notes

- `chatbot_chats` contains `question`, `answer`, comma-separated `question_tag` and `answer_tag`, `user_id`, `session_id`, `llm_model`, `created_at`, `extra` map, `raw_response` JSON string, `app_name`, `os`, and `auto_service_id`.
- `app_events` contains `name`, `created_at`, `user_id`, `params` map, `app_name`, `os`, and related identifiers. Filter chatbot events with `name = 'ai_chat_bot'`.
- For chatbot chat-source distribution, use `chatbot_chats.extra['s']`; normalize absent, null-like, and empty values into an `Unknown` group. The older chat-source question groups by `app_name`, which is a separate label. Event source remains `app_events.app_name`; event labels and chat `extra['s']` labels must not be equated without an explicit, validated mapping.
- Event `params['type']` and `params['action']` describe interactions, not source. Report event volume and distinct users separately from persisted chat messages and chat users; an event is not necessarily a chat.
- Preserve raw labels, note unknown/blank values, and investigate one-off test events before treating small categories as product traffic.
- Timestamps are stored in ClickHouse as UTC; be explicit about the reporting timezone and date boundaries. Existing dashboard charts use `toDate(created_at)`. Check whether a requested time period is rolling days or calendar days in Asia/Tehran.

Existing source analytics for dashboard 37 are maintained by `scripts-py/add_ai_chatbot_source_analytics.py`. Its seven cards cover chat totals, daily chats, daily chat users, event totals, daily events, daily event users, and event action/type by source. Open `https://mt.soupop.ir/dashboard/37-ai-chatbot-analytics-dashboard` to inspect the result.

## Troubleshooting and safe operation

- `401 missing_authorization`: check the saved key/session and permissions; re-run `login` for Agent API routes. Do not log secrets while diagnosing.
- `404 API endpoint does not exist`: use the working standard routes above, not a guessed Agent API route.
- Empty asset search: verify database inventory and metadata directly; a table can exist even when search returns no assets.
- SQL errors: confirm engine and database ID first. PostgreSQL and ClickHouse syntax differ (`count(*)` vs `count()`, JSON operators vs `JSONExtract*`, and map access).
- Dashboard update risk: a `PUT /api/dashboard/{id}` can replace the card list. Read it immediately beforehand and keep existing cards and mappings. Do not clear a dashboard to make room.
- Privacy: prefer aggregate results; restrict exposed chat text, phone numbers, national IDs, and raw JSON to the minimum required. Never expose the API key or session token in a saved question, dashboard description, code, or answer.

## Reusable prompt for a future agent

```text
Use START_HERE.md and AGENTS.md in the Soupop data workspace. On https://mt.soupop.ir, [answer a data question / create saved questions / update dashboard ID].
Use Metabase database [2 Soupop Data / 3 Clickhouse] and these tables: [...].
Business question and metric definitions: [...]. Date period and timezone: [...].
Required filters and chart types: [...]. Preserve existing dashboard content.
Inspect live schema and sample values, validate SQL, save questions, connect filters,
run the saved cards with and without a bounded date range, and give me the question/dashboard links.
Call out missing data, instrumentation mismatches, and assumptions; never print credentials.
```
