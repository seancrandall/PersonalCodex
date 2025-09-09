#!/usr/bin/env python3
"""
Add next/prev linked-list pointers for images and transcribed pages in notes.db.

Idempotent migration:
- Adds note_file.prev_file_id and note_file.next_file_id if missing, with indexes.
- Creates transcribed_page table if missing (with prev_id/next_id and indexes).

Usage:
  python scripts/migrate_notesdb_add_page_links.py --db volumes/notesdb/notes.db
"""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing


NOTE_FILE_PREV_COL = "prev_file_id"
NOTE_FILE_NEXT_COL = "next_file_id"


def column_exists(c: sqlite3.Cursor, table: str, column: str) -> bool:
    c.execute(f"PRAGMA table_info({table})")
    return any(row[1] == column for row in c.fetchall())


def index_exists(c: sqlite3.Cursor, name: str) -> bool:
    c.execute("PRAGMA index_list(note_file)")
    return any(row[1] == name for row in c.fetchall())


def ensure_note_file_links(conn: sqlite3.Connection) -> None:
    with conn:
        c = conn.cursor()
        if not column_exists(c, "note_file", NOTE_FILE_PREV_COL):
            c.execute(
                f"ALTER TABLE note_file ADD COLUMN {NOTE_FILE_PREV_COL} INTEGER REFERENCES file(id) ON DELETE SET NULL"
            )
        if not column_exists(c, "note_file", NOTE_FILE_NEXT_COL):
            c.execute(
                f"ALTER TABLE note_file ADD COLUMN {NOTE_FILE_NEXT_COL} INTEGER REFERENCES file(id) ON DELETE SET NULL"
            )
        # Create indexes if not present
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_note_file_prev ON note_file(note_id, prev_file_id)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_note_file_next ON note_file(note_id, next_file_id)"
        )


def ensure_transcribed_page(conn: sqlite3.Connection) -> None:
    with conn:
        c = conn.cursor()
        # Create table if it doesn't exist
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS transcribed_page (
                id              INTEGER PRIMARY KEY,
                note_id         INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
                file_id         INTEGER REFERENCES file(id) ON DELETE SET NULL,
                page_order      INTEGER NOT NULL,
                text            TEXT,
                json_path       TEXT,
                prev_id         INTEGER REFERENCES transcribed_page(id) ON DELETE SET NULL,
                next_id         INTEGER UNIQUE REFERENCES transcribed_page(id) ON DELETE SET NULL,
                created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (note_id, page_order),
                CHECK (prev_id IS NULL OR prev_id <> id),
                CHECK (next_id IS NULL OR next_id <> id)
            )
            """
        )
        # Indexes
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcribed_page_note_order ON transcribed_page(note_id, page_order)"
        )
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_transcribed_page_file ON transcribed_page(file_id)"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to notes.db")
    args = ap.parse_args()

    with closing(sqlite3.connect(args.db)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_note_file_links(conn)
        ensure_transcribed_page(conn)
    print("Migration complete: linked-list columns and transcribed_page ensured.")


if __name__ == "__main__":
    main()

