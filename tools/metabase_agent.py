#!/usr/bin/env python3
import argparse
import getpass
import json
import os
import sys
from pathlib import Path
from urllib import error, request


# The workspace root holds .env; this file lives in tools/.
ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"
DEFAULT_URL = "https://mt.soupop.ir"


def load_env():
    # Environment variables (e.g. cloud environment secrets) are the fallback; .env wins.
    values = {k: v for k, v in os.environ.items() if k.startswith("METABASE_")}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def save_env(updates):
    current = load_env()
    current.update({k: str(v) for k, v in updates.items() if v is not None})
    ordered = ["METABASE_URL", "METABASE_API_KEY", "METABASE_DATABASE_ID"]
    lines = []
    for key in ordered:
        if key in current:
            lines.append(f"{key}={current[key]}")
    for key in sorted(k for k in current if k not in ordered):
        lines.append(f"{key}={current[key]}")
    ENV_FILE.write_text("\n".join(lines) + "\n")
    try:
        ENV_FILE.chmod(0o600)
    except OSError:
        pass


class MetabaseClient:
    def __init__(self, base_url=None, api_key=None, session_id=None):
        env = load_env()
        self.base_url = (base_url or env.get("METABASE_URL") or DEFAULT_URL).rstrip("/")
        self.api_key = api_key or env.get("METABASE_API_KEY")
        self.session_id = session_id or env.get("METABASE_SESSION_ID")

    def call(self, method, path, body=None, auth=True):
        data = None
        headers = {"Content-Type": "application/json"}
        if auth and self.api_key:
            headers["X-API-Key"] = self.api_key
        if auth and self.session_id:
            headers["X-Metabase-Session"] = self.session_id
        if body is not None:
            data = json.dumps(body).encode("utf-8")
        req = request.Request(self.base_url + path, data=data, headers=headers, method=method)
        try:
            with request.urlopen(req, timeout=60) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else {}
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"Metabase HTTP {exc.code} for {method} {path}:\n{detail}") from exc
        except error.URLError as exc:
            raise SystemExit(f"Could not reach Metabase at {self.base_url}: {exc.reason}") from exc

    def login(self, username, password):
        result = self.call("POST", "/api/session", {"username": username, "password": password}, auth=False)
        session_id = result.get("id")
        if not session_id:
            raise SystemExit(f"Login succeeded but no session id was returned: {result}")
        self.session_id = session_id
        return session_id

    def create_api_key(self, name, group_id):
        return self.call("POST", "/api/api-key", {"name": name, "group_id": group_id})

    def create_collection(self, name, description=None, parent_collection_id=None):
        body = {"name": name}
        if description is not None:
            body["description"] = description
        if parent_collection_id is not None:
            body["parent_collection_id"] = parent_collection_id
        return self.call("POST", "/api/agent/v1/collection", body)

    def ping(self):
        return self.call("GET", "/api/agent/v1/ping")

    def search(self, query):
        return self.call("POST", "/api/agent/v1/search", {"term_queries": query, "semantic_queries": query})

    def list_databases(self):
        return self.call("GET", "/api/database")

    def execute_sql(self, database_id, sql):
        return self.call("POST", "/api/agent/v1/execute-sql", {"database_id": int(database_id), "sql": sql})

    def create_native_card(self, database_id, name, sql, display=None, description=None, collection_id=None, template_tags=None):
        body = {
            "name": name,
            "type": "question",
            "display": display or "table",
            "description": description,
            "visualization_settings": {},
            "dataset_query": {
                "database": int(database_id),
                "type": "native",
                "native": {
                    "query": sql,
                    "template-tags": template_tags or {},
                },
            },
        }
        if collection_id is not None:
            body["collection_id"] = collection_id
        return self.call("POST", "/api/card", body)

    def construct_native_query(self, database_id, sql):
        return self.call("POST", "/api/agent/v1/construct-native-query", {"database_id": int(database_id), "sql": sql})

    def create_question(self, name, query, display=None, description=None, collection_id=None):
        body = {"name": name, "query": query}
        if display is not None:
            body["display"] = display
        if description is not None:
            body["description"] = description
        if collection_id is not None:
            body["collection_id"] = collection_id
        return self.call("POST", "/api/agent/v1/question", body)

    def create_dashboard(self, name, question_ids=None, description=None, collection_id=None):
        body = {"name": name}
        if question_ids:
            body["question_ids"] = [int(qid) for qid in question_ids]
        if description is not None:
            body["description"] = description
        if collection_id is not None:
            body["collection_id"] = collection_id
        return self.call("POST", "/api/agent/v1/dashboard", body)

    def create_standard_dashboard(self, name, description=None, collection_id=None, parameters=None):
        body = {"name": name}
        if description is not None:
            body["description"] = description
        if collection_id is not None:
            body["collection_id"] = collection_id
        if parameters is not None:
            body["parameters"] = parameters
        return self.call("POST", "/api/dashboard", body)

    def update_agent_dashboard(self, dashboard_id, dashcards):
        return self.call("PUT", f"/api/agent/v1/dashboard/{int(dashboard_id)}", {"dashcards": dashcards})

    def update_standard_dashboard_cards(self, dashboard_id, dashcards):
        return self.call("PUT", f"/api/dashboard/{int(dashboard_id)}", {"dashcards": dashcards})

    def read_resource(self, uris):
        return self.call("POST", "/api/agent/v1/read-resource", {"uris": uris})


def print_json(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def command_save_key(args):
    save_env({
        "METABASE_URL": args.url.rstrip("/"),
        "METABASE_API_KEY": args.api_key,
        "METABASE_DATABASE_ID": args.database_id,
    })
    print(f"Saved Metabase settings to {ENV_FILE}")


def command_create_key(args):
    username = args.username or input("Metabase username/email: ")
    password = args.password or getpass.getpass("Metabase password: ")
    client = MetabaseClient(base_url=args.url)
    client.login(username, password)
    result = client.create_api_key(args.name, args.group_id)
    api_key = result.get("key") or result.get("unmasked_key") or result.get("api_key")
    if not api_key:
        print_json(result)
        raise SystemExit("Metabase created/listed a key response, but I could not find the raw key field to save.")
    save_env({
        "METABASE_URL": args.url.rstrip("/"),
        "METABASE_API_KEY": api_key,
        "METABASE_DATABASE_ID": args.database_id,
    })
    print(f"Created and saved API key to {ENV_FILE}")


def command_login(args):
    username = args.username or input("Metabase username/email: ")
    password = args.password or getpass.getpass("Metabase password: ")
    client = MetabaseClient(base_url=args.url)
    session_id = client.login(username, password)
    save_env({
        "METABASE_URL": args.url.rstrip("/"),
        "METABASE_SESSION_ID": session_id,
        "METABASE_DATABASE_ID": args.database_id,
    })
    print(f"Saved Metabase session to {ENV_FILE}")


def build_parser():
    parser = argparse.ArgumentParser(description="Small helper for Soupop Metabase Agent API.")
    sub = parser.add_subparsers(dest="command", required=True)

    save_key = sub.add_parser("save-key", help="Save an existing Metabase API key into .env.")
    save_key.add_argument("--url", default=DEFAULT_URL)
    save_key.add_argument("--api-key", required=True)
    save_key.add_argument("--database-id")
    save_key.set_defaults(func=command_save_key)

    create_key = sub.add_parser("create-key", help="Log in and create/save a Metabase API key.")
    create_key.add_argument("--url", default=DEFAULT_URL)
    create_key.add_argument("--username")
    create_key.add_argument("--password")
    create_key.add_argument("--name", default="Soupop Codex Agent")
    create_key.add_argument("--group-id", type=int, required=True, help="Metabase group id for the API-key user.")
    create_key.add_argument("--database-id")
    create_key.set_defaults(func=command_create_key)

    login = sub.add_parser("login", help="Log in and save a Metabase session id for Agent API calls.")
    login.add_argument("--url", default=DEFAULT_URL)
    login.add_argument("--username")
    login.add_argument("--password")
    login.add_argument("--database-id", default=load_env().get("METABASE_DATABASE_ID"))
    login.set_defaults(func=command_login)

    sub.add_parser("ping", help="Check Agent API connectivity.").set_defaults(
        func=lambda args: print_json(MetabaseClient().ping())
    )

    search = sub.add_parser("search", help="Search Metabase tables, questions, dashboards, and collections.")
    search.add_argument("query")
    search.set_defaults(func=lambda args: print_json(MetabaseClient().search(args.query)))

    sub.add_parser("list-databases", help="List Metabase databases and their ids.").set_defaults(
        func=lambda args: print_json(MetabaseClient().list_databases())
    )

    execute = sub.add_parser("sql", help="Run SQL through /api/agent/v1/execute-sql.")
    execute.add_argument("sql")
    execute.add_argument("--database-id", default=load_env().get("METABASE_DATABASE_ID"), required=not bool(load_env().get("METABASE_DATABASE_ID")))
    execute.set_defaults(func=lambda args: print_json(MetabaseClient().execute_sql(args.database_id, args.sql)))

    construct = sub.add_parser("construct-native", help="Convert SQL into a query handle for saving as a question.")
    construct.add_argument("sql")
    construct.add_argument("--database-id", default=load_env().get("METABASE_DATABASE_ID"), required=not bool(load_env().get("METABASE_DATABASE_ID")))
    construct.set_defaults(func=lambda args: print_json(MetabaseClient().construct_native_query(args.database_id, args.sql)))

    question = sub.add_parser("create-question", help="Create a saved question from a query handle.")
    question.add_argument("--name", required=True)
    question.add_argument("--query", required=True, help="Query handle or base64 query from construct-native.")
    question.add_argument("--display", default=None, help="Optional display type, e.g. table, line, bar, scalar.")
    question.add_argument("--description")
    question.add_argument("--collection-id", type=int)
    question.set_defaults(func=lambda args: print_json(MetabaseClient().create_question(
        args.name, args.query, args.display, args.description, args.collection_id
    )))

    native_card = sub.add_parser("create-native-card", help="Create a saved question directly from native SQL.")
    native_card.add_argument("--name", required=True)
    native_card.add_argument("--sql", required=True)
    native_card.add_argument("--display", default="table")
    native_card.add_argument("--description")
    native_card.add_argument("--collection-id", type=int)
    native_card.add_argument("--database-id", default=load_env().get("METABASE_DATABASE_ID"), required=not bool(load_env().get("METABASE_DATABASE_ID")))
    native_card.set_defaults(func=lambda args: print_json(MetabaseClient().create_native_card(
        args.database_id, args.name, args.sql, args.display, args.description, args.collection_id
    )))

    dashboard = sub.add_parser("create-dashboard", help="Create a dashboard, optionally with question ids.")
    dashboard.add_argument("--name", required=True)
    dashboard.add_argument("--question-id", action="append", dest="question_ids")
    dashboard.add_argument("--description")
    dashboard.add_argument("--collection-id", type=int)
    dashboard.set_defaults(func=lambda args: print_json(MetabaseClient().create_dashboard(
        args.name, args.question_ids, args.description, args.collection_id
    )))

    read = sub.add_parser("read", help="Read metabase:// resources, max 5 per call.")
    read.add_argument("uris", nargs="+")
    read.set_defaults(func=lambda args: print_json(MetabaseClient().read_resource(args.uris)))

    collection = sub.add_parser("create-collection", help="Create a Metabase collection.")
    collection.add_argument("--name", required=True)
    collection.add_argument("--description")
    collection.add_argument("--parent-collection-id", type=int)
    collection.set_defaults(func=lambda args: print_json(MetabaseClient().create_collection(
        args.name, args.description, args.parent_collection_id
    )))

    return parser


if __name__ == "__main__":
    cli = build_parser()
    parsed = cli.parse_args()
    parsed.func(parsed)
