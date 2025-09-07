#!/usr/bin/env python3
"""
Initialize the Standard Works SQLite database at volumes/scripdb/standardworks.db
using the schema in src/scripturedb/schema.sql.

Usage:
  python scripts/init_standardworks_db.py

Optional args:
  --db <path>      Override output DB path (default: volumes/scripdb/standardworks.db)
  --schema <path>  Override schema path (default: src/scripturedb/schema.sql)
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=repo_root / "volumes" / "scripdb" / "standardworks.db",
        help="Output SQLite DB path",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=repo_root / "src" / "scripturedb" / "schema.sql",
        help="Schema SQL file path",
    )
    args = parser.parse_args()

    db_path: Path = args.db
    schema_path: Path = args.schema

    if not schema_path.is_file():
        raise SystemExit(f"Schema not found: {schema_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    sql = schema_path.read_text(encoding="utf-8")

    with sqlite3.connect(db_path) as conn:
        conn.executescript("PRAGMA foreign_keys = ON;")
        conn.executescript(sql)
        conn.commit()

    print(f"Initialized schema into: {db_path}")


if __name__ == "__main__":
    main()

