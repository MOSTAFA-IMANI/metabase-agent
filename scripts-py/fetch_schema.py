#!/usr/bin/env python3
"""Save a compact schema snapshot of the Soupop databases to sql/snapshot/.

A fallback for when Metabase is unreachable; live metadata wins when it is not.
Uses the signed-in session or API key in .env.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

from metabase_agent import MetabaseClient

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "sql" / "snapshot"


def fetch_all():
    """Fetch every configured database and return one summary line per file."""
    lines = []
    config = json.loads((ROOT / "workspace.config.json").read_text())
    client = MetabaseClient(base_url=config["metabase_url"])
    OUT.mkdir(exist_ok=True)
    for name, db_id in config["databases"].items():
        meta = client.call("GET", f"/api/database/{db_id}/metadata")
        tables = []
        for t in sorted(meta.get("tables", []), key=lambda t: (t.get("schema") or "", t["name"])):
            tables.append({
                "table": t["name"],
                "schema": t.get("schema"),
                "description": t.get("description"),
                "columns": [
                    {"name": f["name"], "type": f.get("database_type"), "description": f.get("description")}
                    for f in t.get("fields", [])
                ],
            })
        snapshot = {"database_id": db_id, "engine": meta.get("engine"), "name": meta.get("name"),
                    "fetched_at": datetime.now(timezone.utc).isoformat(), "tables": tables}
        path = OUT / f"{name}.json"
        path.write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n")
        lines.append(f"Saved {len(tables)} tables to {path.relative_to(ROOT)}")
    return lines


def main():
    for line in fetch_all():
        print(line)


if __name__ == "__main__":
    main()
