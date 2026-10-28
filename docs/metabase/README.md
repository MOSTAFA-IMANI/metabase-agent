# Metabase docs: API and MCP

How agents and scripts talk to Metabase at `https://mt.soupop.ir`.

| File | What it is |
|---|---|
| [MCP.md](MCP.md) | Connect Codex (or another agent) to Metabase's built-in MCP server. Staff use this. |
| [API_KEY_SETUP.md](API_KEY_SETUP.md) | Create a limited Metabase group and API key for an assistant, and store it safely |
| [API_RUNBOOK.md](API_RUNBOOK.md) | Analyst runbook for the REST API: credentials, safe routes, dashboard preservation, filters |
| [metabase-openapi.json](metabase-openapi.json) | Metabase REST API OpenAPI spec (static copy; verify against the running instance) |
| [metabase-api-docs.html](metabase-api-docs.html) | Saved copy of the Metabase API documentation page (live: https://www.metabase.com/docs/latest/api) |

Which one to use: MCP when Metabase is version 62 or newer (it is), so each person signs in with their own account and their permissions apply. The REST API through `scripts-py/metabase_agent.py` is the fallback and what the analyst builder scripts use.
