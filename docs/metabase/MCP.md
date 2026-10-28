# Connect an agent to Metabase by MCP

Metabase 62 and newer has a built-in MCP server. An agent connected to it can search Metabase, read table metadata, run SQL and save questions and dashboards, all as the signed-in person, so their own Metabase permissions apply. `https://mt.soupop.ir` runs a version that supports it.

## Codex

During setup Codex does this for the person (see `AGENTS.md`, "Setting up"). To do it by hand:

1. Run `python3 scripts-py/check_setup.py` from the workspace root. It finds the Metabase version and the MCP path and writes them to `.workspace-state.json` (`mode` and `mcp_url`).
2. Open `~/.codex/config.toml` (Windows: `%USERPROFILE%\.codex\config.toml`) and add the block from [`codex/config.toml.example`](../../codex/config.toml.example), with `url` set to `mcp_url`:

   ```toml
   [mcp_servers.metabase]
   url = "https://mt.soupop.ir/api/metabase-mcp"
   ```

3. Quit and reopen the Codex app. The first time it uses Metabase it asks the person to sign in with their own Metabase account.

## Paths

Newer Metabase serves MCP at `/api/metabase-mcp`; some 60.x builds use `/api/mcp`. `workspace.config.json` lists both under `mcp_paths`, and `check_setup.py` records the one that answers.

## If something fails

- **401 or "not signed in":** quit and reopen Codex so it asks for sign-in again. Never paste a password or key into the chat.
- **MCP path not found:** the instance is older than 62. Use API mode: `python3 scripts-py/metabase_agent.py login`, then the commands in [API_RUNBOOK.md](API_RUNBOOK.md).
