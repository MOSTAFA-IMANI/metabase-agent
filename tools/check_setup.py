#!/usr/bin/env python3
"""Check this computer is ready to use Codex with Soupop Metabase.

Runs the launcher's checklist from the command line and writes the result to
.workspace-state.json so Codex knows which connection mode to use.
Standard library only.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from metabase_agent import load_env  # noqa: E402

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


def find_codex():
    path = shutil.which("codex")
    if path:
        try:
            out = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            out = ""
        return {"found": True, "kind": "cli", "path": path, "version": out}
    if platform.system() == "Darwin":
        for app in ("/Applications/Codex.app", str(Path.home() / "Applications/Codex.app")):
            if Path(app).exists():
                return {"found": True, "kind": "app", "path": app, "version": ""}
    return {"found": False}


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


def check_metabase(config, base, state, add):
    # 3. Version decides MCP or API mode.
    _, props = get(base + "/api/session/properties")
    tag = (props or {}).get("version", {}).get("tag") if isinstance(props, dict) else None
    major = major_version(tag)
    mode = "mcp" if major is not None and major >= config.get("mcp_min_major_version", 62) else "api"
    state.update({"metabase_version": tag, "mode": mode})
    add("Metabase version", tag is not None, f"{tag or 'unknown'}: using {mode.upper()} mode")

    # 4. Sign-in.
    if mode == "api":
        env = load_env()
        headers = {}
        if env.get("METABASE_SESSION_ID"):
            headers["X-Metabase-Session"] = env["METABASE_SESSION_ID"]
        if env.get("METABASE_API_KEY"):
            headers["X-API-Key"] = env["METABASE_API_KEY"]
        status, user = get(base + "/api/user/current", headers) if headers else (None, None)
        if status == 200 and isinstance(user, dict):
            add("Metabase sign-in", True, f"signed in as {user.get('email', 'unknown')}")
        else:
            add("Metabase sign-in", False, "not signed in; use the form below or run: python3 tools/metabase_agent.py login")
    else:
        state["mcp_url"] = find_mcp_url(config, base)
        if codex_has_metabase():
            add("Codex connected to Metabase", True, "Codex has the metabase server; it asks you to sign in the first time")
        else:
            add("Codex connected to Metabase", False, "not connected yet; click Connect, then sign in with your Metabase account")


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

    # 2. Metabase reachable. Without it, skip the Metabase checks but still check Codex.
    status, _ = get(base + "/api/health")
    if add("Metabase reachable", status == 200, f"{base} answered" if status == 200 else f"no answer from {base}"):
        check_metabase(config, base, state, add)

    # 5. Codex.
    codex = find_codex()
    state["codex"] = codex
    add("Codex installed", codex["found"],
        f"{codex['kind']} at {codex['path']} {codex.get('version', '')}".strip() if codex["found"]
        else "install the Codex app or CLI from OpenAI")

    # 6. Node.js matters only for installing the Codex CLI with npm.
    if not codex["found"] or codex.get("kind") == "cli":
        node = shutil.which("node")
        add("Node.js", None, f"found at {node}" if node else "not found; only needed to install the Codex CLI with npm")

    if state.get("staff_collection_id") is None:
        add("Staff collection", False, "not set; add it in Settings or in workspace.config.json")
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
