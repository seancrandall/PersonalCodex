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


def ensure_file_processed_flag(conn: sqlite3.Connection) -> None:
    with conn:
        c = conn.cursor()
        # Add boolean-like processed flag if missing
        c.execute("PRAGMA table_info(file)")
        cols = [row[1] for row in c.fetchall()]
        if "fully_processed" not in cols:
            c.execute(
                "ALTER TABLE file ADD COLUMN fully_processed INTEGER NOT NULL DEFAULT 0 CHECK (fully_processed IN (0,1))"
            )
        # Optional: index to quickly find unprocessed files
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_file_fully_processed ON file(fully_processed)"
        )


def ensure_original_filename_and_backfill(conn: sqlite3.Connection) -> None:
    with conn:
        c = conn.cursor()
        c.execute("PRAGMA table_info(file)")
        cols = [row[1] for row in c.fetchall()]
        if "original_filename" not in cols:
            c.execute("ALTER TABLE file ADD COLUMN original_filename TEXT")
        # Backfill from basename(path) where NULL
        # Use Python to compute basenames reliably
        c = conn.cursor()
        c.execute("SELECT id, path FROM file WHERE original_filename IS NULL OR original_filename = ''")
        rows = c.fetchall()
        if rows:
            import os
            for fid, p in rows:
                base = os.path.basename(p) if p else None
                if base:
                    conn.execute("UPDATE file SET original_filename = ? WHERE id = ?", (base, fid))


def ensure_note_source_table(conn: sqlite3.Connection) -> None:
    with conn:
        c = conn.cursor()
        c.execute(
            """
            CREATE TABLE IF NOT EXISTS note_source (
                note_id    INTEGER NOT NULL REFERENCES note(id) ON DELETE CASCADE,
                source_key TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to notes.db")
    args = ap.parse_args()

    with closing(sqlite3.connect(args.db)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        ensure_note_file_links(conn)
        ensure_transcribed_page(conn)
        ensure_file_processed_flag(conn)
        ensure_original_filename_and_backfill(conn)
        ensure_note_source_table(conn)
    print("Migration complete: linked-list columns and transcribed_page ensured.")


if __name__ == "__main__":
    main()
