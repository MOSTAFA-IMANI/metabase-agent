# Metabase API key for the assistant

Instance: https://mt.soupop.ir · default database id: `2`

## 1. Create a dedicated group
Admin settings → People → Groups → **Create a group**, name it `Claude Assistant`. Add no people.

## 2. Grant data permissions (Admin → Permissions → Data)
For the `Claude Assistant` group, on database 2 (and ClickHouse only if needed):

| Setting | Value | Why |
|---|---|---|
| View data | Can view | read rows |
| Create queries | Query builder and native | the assistant writes SQL |
| Download results | No (or 10k rows) | not needed via API |
| Manage table metadata / database | No | not needed |

Permissions are additive across groups: check the **All Users** group isn't granting more than you intend, because the API-key user also inherits from it. To hide sensitive tables (phone numbers, national IDs), set those tables to "Blocked"/no access for this group.

## 3. Grant collection permissions (Admin → Permissions → Collections)
- Create a collection `Claude Assistant` (in Our analytics) and give the group **Curate** on it. This is where it saves questions and dashboards.
- Give **View** on collections whose existing dashboards it should read or copy from.
- Give **Curate** on an existing collection only if you want it to edit dashboards there (e.g. dashboard 37).
- Root "Our analytics": View (not Curate).

Do not add the group to Administrators, and no application permissions (settings, monitoring, subscriptions) are needed.

## 4. Create the key
Admin settings → Settings → Authentication → **API keys** → Create API key. Name `claude-assistant`, group `Claude Assistant`. Copy the key now; Metabase shows it only once.

## 5. Store it (never paste it into chat)
In the Claude app: Project settings → Environment → Cloud environment menu → **Add cloud environment**:
- Environment variables:
  ```
  METABASE_URL=https://mt.soupop.ir
  METABASE_API_KEY=<the key>
  METABASE_DATABASE_ID=2
  ```
- Network access: Limited, add `mt.soupop.ir` under Allowed domains (keep "Allow package managers" ticked). Without this, cloud threads can't reach Metabase at all.

New threads started after saving pick it up. `scripts-py/metabase_agent.py` now reads `METABASE_*` env vars when there is no `.env` file. On your own machine, `python3 scripts-py/metabase_agent.py save-key --api-key ... --database-id 2` still works.

## 6. Verify
`python3 scripts-py/metabase_agent.py search users` and a `sql "select 1"` call. `/api/agent/v1/*` routes may still require a login session (see [API_RUNBOOK.md](API_RUNBOOK.md)); standard `/api/card`, `/api/dashboard`, `/api/dataset` work with the key.

## Rotation
If the key leaks: Admin → API keys → Regenerate, then update the environment variable.
