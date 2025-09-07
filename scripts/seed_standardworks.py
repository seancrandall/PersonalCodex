#!/usr/bin/env python3
"""
Seed the Standard Works volumes and books into the SQLite database.

Default DB path is taken from env STANDARD_WORKS_DB or
`volumes/scripdb/standardworks.db` relative to repo root.

Usage:
  python scripts/seed_standardworks.py
  python scripts/seed_standardworks.py --db path/to/db.sqlite
"""

from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from typing import Iterable, List, Tuple


VOLUMES: List[Tuple[str, List[str]]] = [
    (
        "Old Testament",
        [
            "Genesis",
            "Exodus",
            "Leviticus",
            "Numbers",
            "Deuteronomy",
            "Joshua",
            "Judges",
            "Ruth",
            "1 Samuel",
            "2 Samuel",
            "1 Kings",
            "2 Kings",
            "1 Chronicles",
            "2 Chronicles",
            "Ezra",
            "Nehemiah",
            "Esther",
            "Job",
            "Psalms",
            "Proverbs",
            "Ecclesiastes",
            "Song of Solomon",
            "Isaiah",
            "Jeremiah",
            "Lamentations",
            "Ezekiel",
            "Daniel",
            "Hosea",
            "Joel",
            "Amos",
            "Obadiah",
            "Jonah",
            "Micah",
            "Nahum",
            "Habakkuk",
            "Zephaniah",
            "Haggai",
            "Zechariah",
            "Malachi",
        ],
    ),
    (
        "New Testament",
        [
            "Matthew",
            "Mark",
            "Luke",
            "John",
            "Acts",
            "Romans",
            "1 Corinthians",
            "2 Corinthians",
            "Galatians",
            "Ephesians",
            "Philippians",
            "Colossians",
            "1 Thessalonians",
            "2 Thessalonians",
            "1 Timothy",
            "2 Timothy",
            "Titus",
            "Philemon",
            "Hebrews",
            "James",
            "1 Peter",
            "2 Peter",
            "1 John",
            "2 John",
            "3 John",
            "Jude",
            "Revelation",
        ],
    ),
    (
        "Book of Mormon",
        [
            "1 Nephi",
            "2 Nephi",
            "Jacob",
            "Enos",
            "Jarom",
            "Omni",
            "Words of Mormon",
            "Mosiah",
            "Alma",
            "Helaman",
            "3 Nephi",
            "4 Nephi",
            "Mormon",
            "Ether",
            "Moroni",
        ],
    ),
    (
        "Doctrine and Covenants",
        [
            "Sections",
            "Official Declarations",
        ],
    ),
    (
        "Pearl of Great Price",
        [
            "Moses",
            "Abraham",
            "Joseph Smith—Matthew",
            "Joseph Smith—History",
            "Articles of Faith",
        ],
    ),
]


def ensure_schema(conn: sqlite3.Connection) -> None:
    # Minimal check to ensure required tables exist.
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('volume','book');"
    )
    names = {row[0] for row in cur.fetchall()}
    missing = {"volume", "book"} - names
    if missing:
        raise SystemExit(
            "Database is missing required tables: " + ", ".join(sorted(missing))
        )


def upsert_volume(conn: sqlite3.Connection, name: str) -> int:
    conn.execute("INSERT OR IGNORE INTO volume(VolumeName) VALUES (?)", (name,))
    row = conn.execute("SELECT id FROM volume WHERE VolumeName=?", (name,)).fetchone()
    assert row is not None
    return int(row[0])


def upsert_book(conn: sqlite3.Connection, volume_id: int, name: str) -> int:
    # Use BookName as our canonical key (short title). Also set ShortTitle if empty.
    conn.execute(
        "INSERT OR IGNORE INTO book(fkVolume, BookName, ShortTitle) VALUES (?, ?, ?)",
        (volume_id, name, name),
    )
    row = conn.execute(
        "SELECT id FROM book WHERE fkVolume=? AND BookName=?", (volume_id, name)
    ).fetchone()
    assert row is not None
    return int(row[0])


def seed(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        ensure_schema(conn)
        with conn:  # transaction
            for vol_name, books in VOLUMES:
                vol_id = upsert_volume(conn, vol_name)
                for book_name in books:
                    upsert_book(conn, vol_id, book_name)


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    default_db = os.environ.get(
        "STANDARD_WORKS_DB",
        str(repo_root / "volumes" / "scripdb" / "standardworks.db"),
    )

    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path(default_db))
    args = parser.parse_args()
    seed(args.db)
    print(f"Seeded volumes and books into: {args.db}")


if __name__ == "__main__":
    main()
