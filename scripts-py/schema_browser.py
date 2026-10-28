#!/usr/bin/env python3
import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT / "sql" / "soupop.sql"


def load_schema():
    sql = SQL_FILE.read_text()
    tables = []
    pattern = re.compile(r'CREATE TABLE "public"\."([^"]+)" \((.*?)\n\) WITH', re.S)
    for table_name, body in pattern.findall(sql):
        columns = []
        for line in body.splitlines():
            match = re.match(r'\s+"([^"]+)"\s+([^,]+),?$', line)
            if not match:
                continue
            name, column_type = match.groups()
            if name == "CONSTRAINT":
                continue
            column_type = re.sub(r"\s+DEFAULT\s+.*", "", column_type)
            column_type = column_type.replace(" NOT NULL", "").strip()
            columns.append({"name": name, "type": column_type})
        tables.append({"table": table_name, "columns": columns})
    return tables


def main():
    parser = argparse.ArgumentParser(description="Browse tables/columns from soupop.sql.")
    parser.add_argument("query", nargs="?", help="Filter table or column names.")
    parser.add_argument("--json", action="store_true", help="Print matching schema as JSON.")
    args = parser.parse_args()

    schema = load_schema()
    if args.query:
        needle = args.query.lower()
        schema = [
            table for table in schema
            if needle in table["table"].lower()
            or any(needle in col["name"].lower() for col in table["columns"])
        ]

    if args.json:
        print(json.dumps(schema, ensure_ascii=False, indent=2))
        return

    for table in schema:
        print(table["table"])
        for column in table["columns"]:
            print(f"  {column['name']}: {column['type']}")


if __name__ == "__main__":
    main()

