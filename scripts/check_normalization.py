#!/usr/bin/env python3
"""
CI-friendly check to ensure verse text is normalized (no mojibake, tabs, CRs,
double spaces, or ASCII dot ellipses).

Usage:
  python scripts/check_normalization.py [--db volumes/scripdb/standardworks.db]
Exits nonzero if issues are found; prints counts and a few samples per issue.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import List, Tuple


def q(con: sqlite3.Connection, sql: str, params: Tuple = ()) -> int:
    return int(con.execute(sql, params).fetchone()[0])


def sample(con: sqlite3.Connection, where: str, limit: int = 5) -> List[Tuple[str, str, int, str]]:
    sql = f"""
    SELECT b.BookName, c.ChapterNumber, v.VerseNumber, substr(v.VerseContent,1,120)
    FROM verse v
    JOIN chapter c ON c.id=v.fkChapter
    JOIN book b ON b.id=c.fkBook
    WHERE {where}
    LIMIT {limit}
    """
    return list(con.execute(sql))


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    default_db = os.environ.get(
        "STANDARD_WORKS_DB", str(repo_root / "volumes" / "scripdb" / "standardworks.db")
    )
    ap = argparse.ArgumentParser(description="Check verse text normalization")
    ap.add_argument("--db", type=Path, default=Path(default_db))
    args = ap.parse_args()
    if not args.db.exists():
        raise SystemExit(f"DB not found: {args.db}")

    con = sqlite3.connect(args.db)
    issues = []

    checks = [
        ("mojibake_utf8", "VerseContent LIKE '%â%' OR VerseContent LIKE '%Â%'", "UTF-8 mojibake found"),
        ("tabs", "VerseContent LIKE '%\t%'", "Tab characters found"),
        ("carriage_returns", "VerseContent LIKE '%\r%'", "Carriage returns found"),
        ("double_spaces", "VerseContent LIKE '%  %'", "Double spaces found"),
        ("ascii_ellipsis", "VerseContent LIKE '%...%'", "ASCII ellipses '...' found"),
    ]

    for key, where, desc in checks:
        count = q(con, f"SELECT COUNT(*) FROM verse WHERE {where}")
        if count:
            issues.append((desc, count, where))

    if not issues:
        print("OK: verse text normalized.")
        return

    print("Issues detected:")
    for desc, count, where in issues:
        print(f"- {desc}: {count}")
        for b, ch, vn, txt in sample(con, where):
            print(f"  * {b} {ch}:{vn} — {txt}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()

