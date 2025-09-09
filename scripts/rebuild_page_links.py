#!/usr/bin/env python3
"""
Rebuild next/prev links for images (note_file) and transcribed pages.

By default, processes all notes and sets prev/next pointers based on page_order
ascending. Use --only-missing to only fill NULL pointers. Supports dry-run.

Examples:
  python scripts/rebuild_page_links.py --db volumes/notesdb/notes.db
  python scripts/rebuild_page_links.py --db volumes/notesdb/notes.db --only-missing --dry-run
"""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from typing import Iterable, Tuple


def iter_note_ids(conn: sqlite3.Connection) -> Iterable[int]:
    cur = conn.execute("SELECT id FROM note ORDER BY id")
    for (nid,) in cur.fetchall():
        yield nid


def rebuild_note_file_links(conn: sqlite3.Connection, note_id: int, only_missing: bool) -> Tuple[int, int]:
    rows = conn.execute(
        """
        SELECT file_id, page_order, prev_file_id, next_file_id
        FROM note_file
        WHERE note_id = ?
        ORDER BY page_order ASC, file_id ASC
        """,
        (note_id,),
    ).fetchall()
    updates = 0
    kept = 0
    for i, (file_id, _page_order, prev_id, next_id) in enumerate(rows):
        prev_file = rows[i - 1][0] if i > 0 else None
        next_file = rows[i + 1][0] if i + 1 < len(rows) else None
        if only_missing and prev_id is not None and next_id is not None:
            kept += 1
            continue
        if prev_id != prev_file or next_id != next_file:
            conn.execute(
                "UPDATE note_file SET prev_file_id = ?, next_file_id = ? WHERE note_id = ? AND file_id = ?",
                (prev_file, next_file, note_id, file_id),
            )
            updates += 1
        else:
            kept += 1
    return updates, kept


def rebuild_transcribed_page_links(conn: sqlite3.Connection, note_id: int, only_missing: bool) -> Tuple[int, int]:
    rows = conn.execute(
        """
        SELECT id, page_order, prev_id, next_id
        FROM transcribed_page
        WHERE note_id = ?
        ORDER BY page_order ASC, id ASC
        """,
        (note_id,),
    ).fetchall()
    updates = 0
    kept = 0
    for i, (row_id, _page_order, prev_id, next_id) in enumerate(rows):
        prev_row = rows[i - 1][0] if i > 0 else None
        next_row = rows[i + 1][0] if i + 1 < len(rows) else None
        if only_missing and prev_id is not None and next_id is not None:
            kept += 1
            continue
        if prev_id != prev_row or next_id != next_row:
            conn.execute(
                "UPDATE transcribed_page SET prev_id = ?, next_id = ? WHERE id = ?",
                (prev_row, next_row, row_id),
            )
            updates += 1
        else:
            kept += 1
    return updates, kept


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True, help="Path to notes.db")
    ap.add_argument("--only-missing", action="store_true", help="Only fill when prev/next are NULL")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with closing(sqlite3.connect(args.db)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        total_nf_updates = total_nf_kept = 0
        total_tp_updates = total_tp_kept = 0
        if args.dry_run:
            conn.isolation_level = None  # autocommit off; we'll wrap in a transaction and roll back
            conn.execute("BEGIN")
        try:
            for nid in iter_note_ids(conn):
                nf_updates, nf_kept = rebuild_note_file_links(conn, nid, args.only_missing)
                tp_updates, tp_kept = rebuild_transcribed_page_links(conn, nid, args.only_missing)
                total_nf_updates += nf_updates
                total_nf_kept += nf_kept
                total_tp_updates += tp_updates
                total_tp_kept += tp_kept
            if args.dry_run:
                conn.execute("ROLLBACK")
        finally:
            pass

    print(
        f"note_file: updated={total_nf_updates}, unchanged={total_nf_kept}; "
        f"transcribed_page: updated={total_tp_updates}, unchanged={total_tp_kept}"
    )


if __name__ == "__main__":
    main()

