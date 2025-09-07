#!/usr/bin/env python3
"""
Normalize verse text in-place to fix mojibake and spacing artifacts.

Usage:
  python scripts/normalize_verses.py [--db volumes/scripdb/standardworks.db]
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path

import importlib.util
import sys


def load_importer_module():
    spec = importlib.util.spec_from_file_location(
        "importer", str(Path(__file__).resolve().parent / "import_scriptures.py")
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def normalize_db(db_path: Path) -> int:
    importer = load_importer_module()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    total = 0
    for rowid, text in cur.execute("SELECT rowid, VerseContent FROM verse"):
        normalized = importer.normalize_text(text)
        if normalized != text:
            cur.execute("UPDATE verse SET VerseContent=? WHERE rowid=?", (normalized, rowid))
            total += 1
    con.commit()
    return total


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    default_db = os.environ.get(
        "STANDARD_WORKS_DB", str(repo_root / "volumes" / "scripdb" / "standardworks.db")
    )
    parser = argparse.ArgumentParser(description="Normalize verse content text")
    parser.add_argument("--db", type=Path, default=Path(default_db))
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    changed = normalize_db(args.db)
    print(f"Normalized verses updated: {changed}")


if __name__ == "__main__":
    main()

