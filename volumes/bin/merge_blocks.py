#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


DEFAULT_DB = os.environ.get("NOTES_DB", "/data/notesdb/notes.db")


@dataclass
class MergeResult:
    success: bool
    message: str
    primary_id: Optional[int] = None
    secondary_id: Optional[int] = None
    conflicts: Optional[List[str]] = None
    details: Optional[Dict[str, Any]] = None

    def to_json(self) -> str:
        return json.dumps(
            {
                "success": self.success,
                "message": self.message,
                "primary_id": self.primary_id,
                "secondary_id": self.secondary_id,
                "conflicts": self.conflicts or [],
                "details": self.details or {},
            },
            ensure_ascii=False,
        )


def get_row(conn: sqlite3.Connection, table: str, pk: int) -> Optional[sqlite3.Row]:
    cur = conn.execute(f"SELECT * FROM {table} WHERE id=?", (pk,))
    row = cur.fetchone()
    return row


def date_part(dt: Optional[str]) -> Optional[str]:
    if not dt:
        return None
    # SQLite stores DATETIME as text; prefer the date portion if present
    # Accept formats like 'YYYY-MM-DD', 'YYYY-MM-DD HH:MM:SS'
    return dt.split(" ")[0]


def merge_blocks(conn: sqlite3.Connection, primary_id: int, secondary_id: int) -> MergeResult:
    conn.row_factory = sqlite3.Row

    if primary_id == secondary_id:
        return MergeResult(False, "primary_id and secondary_id are the same")

    p = get_row(conn, "note_block", primary_id)
    s = get_row(conn, "note_block", secondary_id)
    if not p or not s:
        return MergeResult(False, "one or both blocks do not exist", primary_id, secondary_id)

    # Require same note for now to avoid cross-note invariants
    if int(p["note_id"]) != int(s["note_id"]):
        return MergeResult(
            False,
            f"blocks belong to different notes (primary.note_id={p['note_id']} secondary.note_id={s['note_id']})",
            primary_id,
            secondary_id,
        )

    conflicts: List[str] = []
    def _check(field: str):
        if p[field] != s[field]:
            conflicts.append(field)

    # Potentially conflicting fields we will not reconcile automatically beyond what's described
    for f in [
        "file_id",
        "page_number",
        "block_order",
        "block_type",
        "bbox_json",
        "confidence",
        "tokens",
        "created_at",
    ]:
        _check(f)

    # Compute merged content
    p_content = (p["content"] or "").rstrip("\n")
    s_content = (s["content"] or "").lstrip("\n")
    merged_content = p_content
    if p_content and s_content:
        merged_content = p_content + "\n" + s_content
    elif s_content:
        merged_content = s_content

    # Merge tokens: sum when available
    p_tokens = p["tokens"]
    s_tokens = s["tokens"]
    merged_tokens = None
    if isinstance(p_tokens, int) and isinstance(s_tokens, int):
        merged_tokens = p_tokens + s_tokens
    else:
        merged_tokens = p_tokens if p_tokens is not None else s_tokens

    # Merge created_at: choose earliest; preserve the later as an edit_date
    p_created = p["created_at"]
    s_created = s["created_at"]
    merged_created = p_created
    later_date_for_edit: Optional[str] = None
    try:
        # fallback: lexicographic works for ISO timestamps
        if s_created and (not p_created or s_created < p_created):
            # s earlier than p -> make earliest the new created_at
            merged_created = s_created
            # record p as later edit date
            later_date_for_edit = date_part(p_created)
        elif p_created and (not s_created or p_created <= s_created):
            merged_created = p_created
            later_date_for_edit = date_part(s_created) if s_created and s_created != p_created else None
    except Exception:
        merged_created = p_created or s_created
        later_date_for_edit = date_part(s_created or p_created)

    # Determine block ordering to respect adjacency semantics
    p_order = int(p["block_order"]) if p["block_order"] is not None else None
    s_order = int(s["block_order"]) if s["block_order"] is not None else None
    consecutive_forward = (
        p_order is not None and s_order is not None and s_order == p_order + 1
    )
    details: Dict[str, Any] = {"p_order": p_order, "s_order": s_order, "consecutive_forward": consecutive_forward}

    # Start transaction
    with conn:
        # 1) Merge tags
        to_copy = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT tag_id FROM block_tag WHERE note_block_id=?
              EXCEPT
              SELECT tag_id FROM block_tag WHERE note_block_id=?
            )
            """,
            (secondary_id, primary_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO block_tag(note_block_id, tag_id)\n             SELECT ?, tag_id FROM block_tag WHERE note_block_id=?",
            (primary_id, secondary_id),
        )
        details["tags_copied"] = int(to_copy)

        # 2) Merge passages
        to_copy = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT passage_id FROM block_passage WHERE note_block_id=?
              EXCEPT
              SELECT passage_id FROM block_passage WHERE note_block_id=?
            )
            """,
            (secondary_id, primary_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO block_passage(note_block_id, passage_id, relation)\n             SELECT ?, passage_id, relation FROM block_passage WHERE note_block_id=?",
            (primary_id, secondary_id),
        )
        details["passages_copied"] = int(to_copy)

        # 3) Merge embeddings (copy models that primary does not already have)
        to_copy = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT model_id FROM block_embedding WHERE note_block_id=?
              EXCEPT
              SELECT model_id FROM block_embedding WHERE note_block_id=?
            )
            """,
            (secondary_id, primary_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO block_embedding(note_block_id, model_id, vector, created_at)\n             SELECT ?, model_id, vector, created_at FROM block_embedding WHERE note_block_id=?",
            (primary_id, secondary_id),
        )
        details["embeddings_copied"] = int(to_copy)

        # 4) Merge edit dates (copy all secondary dates to primary)
        to_copy = conn.execute(
            """
            SELECT COUNT(*) FROM (
              SELECT edit_date_id FROM block_edit_date WHERE note_block_id=?
              EXCEPT
              SELECT edit_date_id FROM block_edit_date WHERE note_block_id=?
            )
            """,
            (secondary_id, primary_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO block_edit_date(note_block_id, edit_date_id)\n             SELECT ?, edit_date_id FROM block_edit_date WHERE note_block_id=?",
            (primary_id, secondary_id),
        )
        details["edit_dates_copied"] = int(to_copy)

        # 4b) Preserve the later created_at as a changed date (if applicable)
        if later_date_for_edit:
            conn.execute("INSERT OR IGNORE INTO edit_date(edit_date) VALUES (DATE(?))", (later_date_for_edit,))
            conn.execute(
                "INSERT OR IGNORE INTO block_edit_date(note_block_id, edit_date_id)\n                 SELECT ?, id FROM edit_date WHERE edit_date = DATE(?)",
                (primary_id, later_date_for_edit),
            )

        # 5) Repoint block links (avoid creating self-links; dedupe via INSERT OR IGNORE)
        # from secondary -> primary (label-aware)
        if consecutive_forward:
            # Keep primary's prev; adopt secondary's next and other labels
            from_count = conn.execute(
                "SELECT COUNT(*) FROM note_block_link WHERE from_block_id=? AND to_block_id<>? AND (label IS NULL OR label <> 'prev')",
                (secondary_id, primary_id),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO note_block_link(from_block_id, to_block_id, label, created_at)\n                 SELECT ?, to_block_id, label, created_at FROM note_block_link\n                 WHERE from_block_id=? AND to_block_id<>? AND (label IS NULL OR label <> 'prev')",
                (primary_id, secondary_id, primary_id),
            )
        else:
            # Keep both prev and next from primary; exclude both when copying
            from_count = conn.execute(
                "SELECT COUNT(*) FROM note_block_link WHERE from_block_id=? AND to_block_id<>? AND (label IS NULL OR label NOT IN ('prev','next'))",
                (secondary_id, primary_id),
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO note_block_link(from_block_id, to_block_id, label, created_at)\n                 SELECT ?, to_block_id, label, created_at FROM note_block_link\n                 WHERE from_block_id=? AND to_block_id<>? AND (label IS NULL OR label NOT IN ('prev','next'))",
                (primary_id, secondary_id, primary_id),
            )
        conn.execute("DELETE FROM note_block_link WHERE from_block_id=?", (secondary_id,))

        # to secondary -> primary
        to_count = conn.execute(
            "SELECT COUNT(*) FROM note_block_link WHERE to_block_id=? AND from_block_id<>?",
            (secondary_id, primary_id),
        ).fetchone()[0]
        conn.execute(
            "INSERT OR IGNORE INTO note_block_link(from_block_id, to_block_id, label, created_at)\n             SELECT from_block_id, ?, label, created_at FROM note_block_link WHERE to_block_id=? AND from_block_id<>?",
            (primary_id, secondary_id, primary_id),
        )
        conn.execute("DELETE FROM note_block_link WHERE to_block_id=?", (secondary_id,))

        details["links_from_repointed"] = int(from_count)
        details["links_to_repointed"] = int(to_count)

        # 6) Update primary content/tokens/created_at
        conn.execute(
            "UPDATE note_block SET content=?, tokens=?, created_at=? WHERE id=?",
            (merged_content, merged_tokens, merged_created, primary_id),
        )

        # 7) Delete secondary block (cascades will clean up any remaining references)
        conn.execute("DELETE FROM note_block WHERE id=?", (secondary_id,))

    # Policy summary to help callers understand what we reconciled
        details["policy"] = {
            "content": "primary.content + '\n' + secondary.content",
            "tokens": "sum when both present, else prefer non-null",
            "created_at": "earliest of the two; later date recorded into block_edit_date",
            "links": (
                "consecutive: keep primary.prev, adopt secondary.next; "
                "non-consecutive: keep primary.prev/next; always repoint incoming to primary"
            ),
            "tags/passages": "union (INSERT OR IGNORE)",
            "embeddings": "copy models not already present on primary",
        }

    return MergeResult(
        True,
        "merged",
        primary_id=primary_id,
        secondary_id=secondary_id,
        conflicts=conflicts,
        details=details,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge a secondary note_block into a primary note_block")
    ap.add_argument("--db", default=DEFAULT_DB, help="Path to notes.db (default: env NOTES_DB or /data/notesdb/notes.db)")
    ap.add_argument("--primary", type=int, required=True, help="Primary note_block id to keep")
    ap.add_argument("--secondary", type=int, required=True, help="Secondary note_block id to merge and delete")
    args = ap.parse_args()

    try:
        with closing(sqlite3.connect(args.db)) as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            res = merge_blocks(conn, args.primary, args.secondary)
            print(res.to_json())
            return 0 if res.success else 1
    except Exception as e:
        err = MergeResult(False, f"exception: {e}")
        print(err.to_json())
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
