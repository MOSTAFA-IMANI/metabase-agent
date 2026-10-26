#!/usr/bin/env python3
"""Soupop quick-start launcher.

A small local web app: it serves launcher/ui/ on 127.0.0.1 and runs the setup
steps (checks, Metabase sign-in, updates, schema snapshot, open Codex) for the
page. Standard library only, so it runs on a stock Mac with python3.
"""
import json
import platform
import secrets
import shlex
import subprocess
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI_DIR = Path(__file__).resolve().parent / "ui"
sys.path.insert(0, str(ROOT / "tools"))

import check_setup  # noqa: E402
import fetch_schema  # noqa: E402
from metabase_agent import MetabaseClient, save_env  # noqa: E402

# Every API call must carry this token, so other web pages open in the browser
# cannot drive the launcher through localhost.
TOKEN = secrets.token_urlsafe(24)
EDITABLE_CONFIG = {"requires_vpn": bool, "staff_collection_id": int}
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript"}


def run(cmd, timeout=120):
    try:
        out = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return out.returncode == 0, (out.stdout + out.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def prompt_cards():
    cards, section = [], ""
    for line in (ROOT / "prompts" / "prompt-cards.md").read_text().splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
        elif line[:1].isdigit() and ". " in line and section != "Tips":
            cards.append({"section": section, "text": line.split(". ", 1)[1].strip()})
    return cards


def open_codex():
    state = check_setup.find_codex()
    if not state["found"]:
        return False, "Codex is not installed yet. Install the Codex app from OpenAI, then try again."
    if platform.system() != "Darwin":
        return False, f"Open Codex yourself in this folder: {ROOT}"
    if state["kind"] == "app":
        return run(["open", "-a", state["path"], str(ROOT)])
    script = f'tell application "Terminal" to do script "cd {shlex.quote(str(ROOT))} && codex"'
    ok, out = run(["osascript", "-e", script, "-e", 'tell application "Terminal" to activate'])
    return ok, out or "Opened Codex in Terminal."


def update_config(changes):
    config = json.loads(check_setup.CONFIG_FILE.read_text())
    for key, value in changes.items():
        kind = EDITABLE_CONFIG.get(key)
        if kind is None:
            raise ValueError(f"{key} can't be changed here")
        config[key] = None if value in ("", None) and kind is int else kind(value)
    check_setup.CONFIG_FILE.write_text(json.dumps(config, indent=2) + "\n")
    return config


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the terminal quiet; request bodies may hold passwords

    def send(self, status, body, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def authorized(self):
        if self.headers.get("X-Launcher-Token") != TOKEN:
            self.send(403, {"ok": False, "message": "Reload the launcher page."})
            return False
        return True

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (UI_DIR / "index.html").read_text().replace("__LAUNCHER_TOKEN__", TOKEN)
            return self.send(200, html.encode("utf-8"), CONTENT_TYPES[".html"])
        if not self.path.startswith("/api/"):
            return self.send(404, {"ok": False})
        if not self.authorized():
            return
        if self.path == "/api/checks":
            state = check_setup.check_and_save()
            state["config"] = check_setup.load_config()
            state["workspace"] = str(ROOT)
            return self.send(200, state)
        if self.path == "/api/prompts":
            return self.send(200, {"cards": prompt_cards()})
        return self.send(404, {"ok": False})

    def do_POST(self):
        if not self.authorized():
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self.send(400, {"ok": False, "message": "Bad request"})
        try:
            if self.path == "/api/login":
                url = check_setup.load_config()["metabase_url"]
                session_id = MetabaseClient(base_url=url).login(body.get("username", ""), body.get("password", ""))
                save_env({"METABASE_URL": url, "METABASE_SESSION_ID": session_id})
                return self.send(200, {"ok": True, "message": "Signed in to Metabase."})
            if self.path == "/api/update":
                ok, out = run(["git", "pull", "--ff-only"])
                return self.send(200, {"ok": ok, "message": out or "Up to date."})
            if self.path == "/api/schema":
                return self.send(200, {"ok": True, "message": "\n".join(fetch_schema.fetch_all())})
            if self.path == "/api/open-codex":
                ok, out = open_codex()
                return self.send(200, {"ok": ok, "message": out or "Codex is opening."})
            if self.path == "/api/config":
                update_config(body)
                return self.send(200, {"ok": True, "message": "Saved."})
        except SystemExit as exc:  # MetabaseClient reports HTTP and network errors this way
            msg = str(exc)
            if "HTTP 401" in msg or "HTTP 400" in msg:
                msg = "Metabase did not accept that username or password."
            return self.send(200, {"ok": False, "message": msg})
        except (ValueError, TypeError) as exc:
            return self.send(400, {"ok": False, "message": str(exc)})
        return self.send(404, {"ok": False})


def main():
    server = None
    for port in range(8765, 8785):
        try:
            server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            break
        except OSError:
            continue
    if server is None:
        sys.exit("No free port between 8765 and 8784.")
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"Soupop launcher is running at {url}\nLeave this window open. Press Ctrl+C to stop.")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
