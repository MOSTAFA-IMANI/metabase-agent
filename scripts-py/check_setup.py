#!/usr/bin/env python3
"""Check this computer is ready to use Codex with Soupop Metabase.

Codex runs this during setup (see AGENTS.md). It writes the result to
.workspace-state.json so Codex knows which connection mode to use.
Standard library only.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metabase_agent import MetabaseClient, load_env  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "workspace.config.json"
STATE_FILE = ROOT / ".workspace-state.json"


def get(url, headers=None, timeout=5):
    req = request.Request(url, headers=headers or {}, method="GET")
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, (json.loads(raw) if raw.strip().startswith(("{", "[")) else raw)
    except error.HTTPError as exc:
        return exc.code, None
    except (error.URLError, TimeoutError, OSError):
        return None, None


def major_version(tag):
    # Metabase tags look like v0.56.3 (OSS) or v1.56.3 (EE); the second number is the release.
    match = re.match(r"v?\d+\.(\d+)", tag or "")
    return int(match.group(1)) if match else None


CODEX_CONFIG = Path.home() / ".codex" / "config.toml"


def find_mcp_url(config, base):
    # The MCP route moved between releases; the first path that isn't a 404 wins.
    for path in config.get("mcp_paths", []):
        status, _ = get(base + path)
        if status is not None and status != 404:
            return base + path
    return base + config.get("mcp_paths", ["/api/metabase-mcp"])[0]


def codex_has_metabase():
    try:
        return "[mcp_servers.metabase]" in CODEX_CONFIG.read_text()
    except OSError:
        return False


def has_credentials(env):
    return bool(env.get("METABASE_API_KEY") or env.get("METABASE_SESSION_ID")
                or (env.get("METABASE_USERNAME") and env.get("METABASE_PASSWORD")))


def check_connection(config, state, add):
    """Sign in with the saved key or username and password, and check SQL access."""
    client = MetabaseClient(base_url=state["metabase_url"])
    conn = {"ok": False, "auth": "api_key" if client.api_key else "password",
            "checked_at": state["checked_at"]}
    state["connection"] = conn
    try:
        user = client.call("GET", "/api/user/current")
    except SystemExit as exc:
        msg = str(exc)
        conn["error"] = ("Metabase did not accept the saved API key or password; enter it again on the start page."
                         if "HTTP 401" in msg or "HTTP 400" in msg else msg.splitlines()[0])
        add("Metabase sign-in", False, conn["error"])
        return
    conn.update(ok=True, user=user.get("email") or user.get("common_name") or "API key")
    add("Metabase sign-in", True, f"signed in as {conn['user']}")

    # SQL questions need native query access ("write") on each database.
    try:
        dbs = client.list_databases()
    except SystemExit as exc:
        add("SQL access", False, f"couldn't list databases: {str(exc).splitlines()[0]}")
        return
    dbs = dbs.get("data", []) if isinstance(dbs, dict) else dbs
    by_id = {db.get("id"): db for db in dbs}
    access = {}
    for name, db_id in config.get("databases", {}).items():
        db = by_id.get(db_id)
        access[str(db_id)] = {"name": (db or {}).get("name", name), "visible": db is not None,
                              "sql": (db or {}).get("native_permissions") == "write"}
    conn["sql_access"] = access
    missing = [f"{a['name']} ({i})" for i, a in access.items() if not a["sql"]]
    add("SQL access", not missing,
        "can run SQL on every database" if not missing else
        "no SQL access to " + ", ".join(missing) + "; ask a Metabase admin to give your group native query access")


def check_metabase(config, base, state, add):
    # 3. Version. Saved credentials (start page) mean API mode; otherwise MCP when Metabase supports it.
    _, props = get(base + "/api/session/properties")
    tag = (props or {}).get("version", {}).get("tag") if isinstance(props, dict) else None
    major = major_version(tag)
    supports_mcp = major is not None and major >= config.get("mcp_min_major_version", 62)
    saved = has_credentials(load_env())
    mode = "api" if saved or not supports_mcp else "mcp"
    state.update({"metabase_version": tag, "mode": mode})
    add("Metabase version", tag is not None, f"{tag or 'unknown'}: using {mode.upper()} mode")

    # 4. Sign-in.
    if mode == "api":
        if saved:
            check_connection(config, state, add)
        else:
            add("Metabase sign-in", False, "not signed in; save an API key or your username and password on the start page")
    else:
        state["mcp_url"] = find_mcp_url(config, base)
        if codex_has_metabase():
            add("Codex connected to Metabase", True, "Codex has the metabase server; it asks you to sign in the first time")
        else:
            add("Codex connected to Metabase", False, "not connected yet; add the metabase server to Codex (AGENTS.md, Setting up)")


def run_checks(config):
    base = config["metabase_url"].rstrip("/")
    results = []
    state = {"checked_at": datetime.now(timezone.utc).isoformat(), "metabase_url": base,
             "staff_collection_id": config.get("staff_collection_id")}

    def add(name, ok, detail):
        results.append({"check": name, "ok": ok, "detail": detail})
        return ok

    # 1. VPN, only when the config says Metabase sits behind it.
    if config.get("requires_vpn"):
        status, _ = get(config.get("vpn_probe_url") or base + "/api/health")
        add("VPN", status is not None, "connected" if status else "can't reach the internal network; turn on the org VPN")
    else:
        add("VPN", None, "not required (requires_vpn is false)")

    # 2. Metabase reachable. Without it, skip the Metabase checks.
    status, _ = get(base + "/api/health")
    if add("Metabase reachable", status == 200, f"{base} answered" if status == 200 else f"no answer from {base}"):
        check_metabase(config, base, state, add)

    return results, state


def load_config():
    config = json.loads(CONFIG_FILE.read_text())
    if os.environ.get("SOUPOP_REQUIRES_VPN") in ("0", "1"):
        config["requires_vpn"] = os.environ["SOUPOP_REQUIRES_VPN"] == "1"
    return config


def check_and_save():
    results, state = run_checks(load_config())
    state["checks"] = results
    STATE_FILE.write_text(json.dumps(state, indent=2) + "\n")
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Print machine-readable results.")
    args = parser.parse_args()

    state = check_and_save()
    results = state["checks"]

    if args.json:
        print(json.dumps(state, indent=2))
    else:
        marks = {True: "OK  ", False: "FIX ", None: "--  "}
        for r in results:
            print(f"{marks[r['ok']]} {r['check']}: {r['detail']}")
    sys.exit(1 if any(r["ok"] is False for r in results) else 0)


if __name__ == "__main__":
    main()
