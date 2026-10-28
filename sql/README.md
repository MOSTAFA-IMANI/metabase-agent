# Database schema

| Path | What it is |
|---|---|
| `soupop.sql` | PostgreSQL 15 schema dump of database 2 (Soupop Data), made with Adminer: tables, columns and indexes, no rows. Point in time; live Metabase metadata wins. |
| `snapshot/` | Compact JSON snapshot of databases 2 and 3 from `python3 scripts-py/fetch_schema.py`, for when Metabase is unreachable. Git-ignored. |

Browse the dump without Metabase: `python3 scripts-py/schema_browser.py --help`. ClickHouse (database 3) has no dump here; use `DESCRIBE TABLE chatbot_chats` or the snapshot.
