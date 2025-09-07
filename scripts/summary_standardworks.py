#!/usr/bin/env python3
"""
Summarize the Standard Works database: counts by volume (books, chapters, verses)
and overall totals.

Usage:
  python scripts/summary_standardworks.py
  python scripts/summary_standardworks.py --db volumes/scripdb/standardworks.db
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path


def summarize(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    rows = list(
        cur.execute(
            """
            SELECT v.VolumeName,
                   COUNT(DISTINCT b.id) AS books,
                   COUNT(DISTINCT c.id) AS chapters,
                   COUNT(DISTINCT vv.id) AS verses
            FROM volume v
            LEFT JOIN book b ON b.fkVolume = v.id
            LEFT JOIN chapter c ON c.fkBook = b.id
            LEFT JOIN verse vv ON vv.fkChapter = c.id
            GROUP BY v.id
            ORDER BY v.id
            """
        )
    )

    total_books = sum(r[1] for r in rows)
    total_chapters = sum(r[2] for r in rows)
    total_verses = sum(r[3] for r in rows)

    print("Standard Works Summary")
    print("=======================")
    for vol, books, chapters, verses in rows:
        print(f"- {vol}: {books} books, {chapters} chapters, {verses} verses")
    print("-")
    print(
        f"Total: {total_books} books, {total_chapters} chapters, {total_verses} verses"
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    default_db = os.environ.get(
        "STANDARD_WORKS_DB",
        str(repo_root / "volumes" / "scripdb" / "standardworks.db"),
    )
    parser = argparse.ArgumentParser(description="Summarize Standard Works DB")
    parser.add_argument("--db", type=Path, default=Path(default_db))
    args = parser.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")
    summarize(args.db)


if __name__ == "__main__":
    main()

