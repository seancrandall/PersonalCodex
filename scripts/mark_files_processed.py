#!/usr/bin/env python3
"""
Mark image files as fully processed in notes.db.

Options:
  --all-ocr      Mark files with non-null OCR artifacts (ocr_text_path or ocr_json_path).
  --paths P..    Mark specific file paths.
  --ids I..      Mark specific file ids.
  --unset        Unset instead of setting the flag.

Examples:
  python scripts/mark_files_processed.py --db volumes/notesdb/notes.db --all-ocr
  python scripts/mark_files_processed.py --db volumes/notesdb/notes.db --paths /data/images/a.png /data/images/b.png
"""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--all-ocr", action="store_true")
    ap.add_argument("--paths", nargs="*")
    ap.add_argument("--ids", nargs="*", type=int)
    ap.add_argument("--unset", action="store_true")
    args = ap.parse_args()

    with closing(sqlite3.connect(args.db)) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        flag = 0 if args.unset else 1
        updated = 0
        with conn:
            if args.all_ocr:
                cur = conn.execute(
                    "UPDATE file SET fully_processed = ? WHERE (ocr_text_path IS NOT NULL OR ocr_json_path IS NOT NULL)",
                    (flag,),
                )
                updated += cur.rowcount if cur.rowcount is not None else 0
            if args.paths:
                cur = conn.executemany(
                    "UPDATE file SET fully_processed = ? WHERE path = ?",
                    [(flag, p) for p in args.paths],
                )
                updated += cur.rowcount if cur.rowcount is not None else 0
            if args.ids:
                cur = conn.executemany(
                    "UPDATE file SET fully_processed = ? WHERE id = ?",
                    [(flag, i) for i in args.ids],
                )
                updated += cur.rowcount if cur.rowcount is not None else 0
        print(f"Updated fully_processed for {updated} files.")


if __name__ == "__main__":
    main()

