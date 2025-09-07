#!/usr/bin/env python3
"""
Validate and optionally enrich notes passages by attaching the Standard Works DB.

Checks:
- Every passage.start_verse_id and end_verse_id exists in std.verse(id)
- Optionally fills passage.citation when missing using std.allverses

Usage:
  python scripts/validate_notes_passages.py --notes-db volumes/notesdb/notes.db --std-db volumes/scripdb/standardworks.db [--fill-citations] [--dry-run]
"""
from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing


def get_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--notes-db", default="volumes/notesdb/notes.db")
    p.add_argument("--std-db", default="volumes/scripdb/standardworks.db")
    p.add_argument("--fill-citations", action="store_true", help="Populate missing passage.citation from std.allverses")
    p.add_argument("--dry-run", action="store_true", help="Report actions without writing changes")
    return p.parse_args()


def validate_passages(conn: sqlite3.Connection) -> tuple[int, int]:
    cur = conn.cursor()
    # Missing start ids
    cur.execute(
        """
        SELECT p.id, p.start_verse_id
        FROM passage p
        LEFT JOIN std.verse v ON v.id = p.start_verse_id
        WHERE v.id IS NULL
        ORDER BY p.id
        """
    )
    missing_start = cur.fetchall()

    # Missing end ids
    cur.execute(
        """
        SELECT p.id, p.end_verse_id
        FROM passage p
        LEFT JOIN std.verse v ON v.id = p.end_verse_id
        WHERE v.id IS NULL
        ORDER BY p.id
        """
    )
    missing_end = cur.fetchall()

    if missing_start:
        print(f"Missing start_verse_id in std.verse for {len(missing_start)} passages: {[pid for pid, _ in missing_start][:10]}...")
    if missing_end:
        print(f"Missing end_verse_id in std.verse for {len(missing_end)} passages: {[pid for pid, _ in missing_end][:10]}...")
    if not missing_start and not missing_end:
        print("All passage verse ids present in std.verse ✓")

    return len(missing_start), len(missing_end)


def fetch_citation_parts(conn: sqlite3.Connection, verse_id: int) -> tuple[str, int, int]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT av.BookName, av.ChapterNumber, av.VerseNumber
        FROM std.allverses av
        WHERE av.verse_id = ?
        """,
        (verse_id,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError(f"Verse id {verse_id} not found in std.allverses")
    return row[0], int(row[1]), int(row[2])


def build_citation(start: tuple[str, int, int], end: tuple[str, int, int]) -> str:
    sb, sc, sv = start
    eb, ec, ev = end
    if (sb, sc) == (eb, ec):
        if sv == ev:
            return f"{sb} {sc}:{sv}"
        return f"{sb} {sc}:{sv}–{ev}"
    # Cross-chapter or cross-book
    return f"{sb} {sc}:{sv} – {eb} {ec}:{ev}"


def fill_missing_citations(conn: sqlite3.Connection, dry_run: bool = False) -> int:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, start_verse_id, end_verse_id
        FROM passage
        WHERE citation IS NULL OR TRIM(citation) = ''
        ORDER BY id
        """
    )
    updates = 0
    for pid, svid, evid in cur.fetchall():
        try:
            start = fetch_citation_parts(conn, int(svid))
            end = fetch_citation_parts(conn, int(evid))
            citation = build_citation(start, end)
        except Exception as e:
            print(f"Passage {pid}: cannot build citation ({e})")
            continue
        print(f"Passage {pid}: citation -> {citation}")
        if not dry_run:
            cur.execute("UPDATE passage SET citation = ? WHERE id = ?", (citation, pid))
            updates += 1
    if not dry_run:
        conn.commit()
    return updates


def main() -> None:
    args = get_args()
    with closing(sqlite3.connect(args.notes_db)) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute(f"ATTACH DATABASE '{args.std_db}' AS std;")
        ms, me = validate_passages(conn)
        if args.fill_citations:
            count = fill_missing_citations(conn, dry_run=args.dry_run)
            if args.dry_run:
                print(f"[dry-run] Would update {count} passage.citation values")
            else:
                print(f"Updated {count} passage.citation values")
        # Summary
        print("Summary:")
        print(f"  Missing starts: {ms}")
        print(f"  Missing ends:   {me}")


if __name__ == "__main__":
    main()

