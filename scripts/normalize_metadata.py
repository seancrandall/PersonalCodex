#!/usr/bin/env python3
"""
Normalize chapter headings and book metadata (LongTitle, BookHeading, ShortTitle).

Usage:
  python scripts/normalize_metadata.py [--db volumes/scripdb/standardworks.db]
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


def run(db_path: Path) -> dict:
    imp = load_importer_module()
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    stats = {"chapters": 0, "books": 0}

    # Normalize ChapterHeading
    rows = cur.execute(
        "SELECT rowid, ChapterHeading FROM chapter WHERE ChapterHeading IS NOT NULL"
    ).fetchall()
    for rowid, heading in rows:
        norm = imp.normalize_text(heading)
        if norm != heading:
            cur.execute(
                "UPDATE chapter SET ChapterHeading=? WHERE rowid=?", (norm, rowid)
            )
            stats["chapters"] += 1

    # Normalize book metadata
    book_rows = cur.execute(
        "SELECT rowid, ShortTitle, LongTitle, BookHeading FROM book"
    ).fetchall()
    for rowid, short, longt, bh in book_rows:
        short_n = imp.normalize_text(short) if short else short
        long_n = imp.normalize_text(longt) if longt else longt
        bh_n = imp.normalize_text(bh) if bh else bh
        if short_n != short or long_n != longt or bh_n != bh:
            cur.execute(
                "UPDATE book SET ShortTitle=?, LongTitle=?, BookHeading=? WHERE rowid=?",
                (short_n, long_n, bh_n, rowid),
            )
            stats["books"] += 1

    con.commit()
    return stats


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    default_db = os.environ.get(
        "STANDARD_WORKS_DB", str(repo_root / "volumes" / "scripdb" / "standardworks.db")
    )
    ap = argparse.ArgumentParser(description="Normalize headings and book metadata")
    ap.add_argument("--db", type=Path, default=Path(default_db))
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    stats = run(args.db)
    print(f"Updated chapter headings: {stats['chapters']}, book metadata: {stats['books']}")


if __name__ == "__main__":
    main()
