#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import re
import sqlite3
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DEFAULT_NOTES_DB = os.environ.get("NOTES_DB", "/data/notesdb/notes.db")
DEFAULT_SCHEMA = Path("src/notesdb/schema.sql")
DEFAULT_TXT_DIR = Path(os.environ.get("TXT_DIR", "/data/txt"))
DEFAULT_OCR_DIR = Path(os.environ.get("OCR_DIR", "/data/ocr"))
DEFAULT_IMAGES_DIR = Path(os.environ.get("IMAGES_DIR", "/data/images"))
DEFAULT_STD_DB = os.environ.get("STANDARD_WORKS_DB", "/data/scripdb/standardworks.db")
DEFAULT_ALIASES = os.environ.get("BOOK_ALIASES", "/data/scripdb/book_aliases.json")


# -----------------------------
# Date parsing (from notesdb-dates)
# -----------------------------
MONTHS = {
    "jan": 1, "january": 1,
    "feb": 2, "february": 2,
    "mar": 3, "march": 3,
    "apr": 4, "april": 4,
    "may": 5,
    "jun": 6, "june": 6,
    "jul": 7, "july": 7,
    "aug": 8, "august": 8,
    "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10,
    "nov": 11, "november": 11,
    "dec": 12, "december": 12,
}

ISO_RE = re.compile(r"\b(19\d{2}|20\d{2})[-/\.](0?[1-9]|1[0-2])[-/\.](0?[1-9]|[12]\d|3[01])\b")
NUM_RE = re.compile(r"\b(0?[1-9]|1[0-2])[\-\./_](0?[1-9]|[12]\d|3[01])[\-\./_](\d{2,4}|'\d{2}|’\d{2})\b")
NAME1_RE = re.compile(
    r"\b(\w{3,9})\.?,?\s+([0-3]?\d)(?:st|nd|rd|th)?(?:,)?\s+(\d{2,4}|'\d{2}|’\d{2})\b",
    re.IGNORECASE,
)
NAME2_RE = re.compile(
    r"\b([0-3]?\d)(?:st|nd|rd|th)?\s+(\w{3,9})\.?,?\s+(\d{2,4}|'\d{2}|’\d{2})\b",
    re.IGNORECASE,
)
COMPACT_YMD_RE = re.compile(r"\b(19\d{2}|20\d{2})(0[1-9]|1[0-2])([012]\d|3[01])\b")
YM_ISO_RE = re.compile(r"\b(19\d{2}|20\d{2})[-/\.](0?[1-9]|1[0-2])\b")
MY_NAME_RE = re.compile(r"\b(\w{3,9})\.?,?\s+(\d{2,4}|'\d{2}|’\d{2})\b", re.IGNORECASE)
Y_ONLY_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")


def _pad(n: int) -> str:
    return f"{n:02d}"


def _normalize_year(y: int) -> int:
    if y < 100:
        return 2000 + y if y <= 49 else 1900 + y
    return y


def _valid_date(y: int, m: int, d: int) -> bool:
    try:
        datetime(_normalize_year(y), m, d)
        return True
    except ValueError:
        return False


def _parse_yy_fragment(val: str) -> int:
    val = val.strip().lstrip("'").lstrip("’")
    try:
        return int(val)
    except Exception:
        return 0


def parse_date_str(s: str) -> Optional[tuple[str, str]]:
    if not s:
        return None
    m = ISO_RE.search(s)
    if m:
        y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(y, mo, da):
            return f"{_normalize_year(y)}-{_pad(mo)}-{_pad(da)}", "day"
    m = NAME1_RE.search(s)
    if m:
        mon = MONTHS.get(m.group(1).lower().rstrip('.'), None)
        if mon:
            d = int(m.group(2))
            y = _parse_yy_fragment(m.group(3))
            if _valid_date(y, mon, d):
                return f"{_normalize_year(y)}-{_pad(mon)}-{_pad(d)}", "day"
    m = NAME2_RE.search(s)
    if m:
        d = int(m.group(1))
        mon = MONTHS.get(m.group(2).lower().rstrip('.'), None)
        y = _parse_yy_fragment(m.group(3))
        if mon and _valid_date(y, mon, d):
            return f"{_normalize_year(y)}-{_pad(mon)}-{_pad(d)}", "day"
    m = NUM_RE.search(s)
    if m:
        mo, da, yfrag = int(m.group(1)), int(m.group(2)), _parse_yy_fragment(m.group(3))
        y = yfrag
        if _valid_date(y, mo, da):
            return f"{_normalize_year(y)}-{_pad(mo)}-{_pad(da)}", "day"
    m = COMPACT_YMD_RE.search(s)
    if m:
        y, mo, da = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if _valid_date(y, mo, da):
            return f"{_normalize_year(y)}-{_pad(mo)}-{_pad(da)}", "day"
    m = YM_ISO_RE.search(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 1 <= mo <= 12:
            return f"{_normalize_year(y)}-{_pad(mo)}-01", "month"
    m = MY_NAME_RE.search(s)
    if m:
        mon = MONTHS.get(m.group(1).lower().rstrip('.'), None)
        y = _parse_yy_fragment(m.group(2))
        if mon and y:
            return f"{_normalize_year(y)}-{_pad(mon)}-01", "month"
    m = Y_ONLY_RE.search(s)
    if m:
        y = int(m.group(1))
        return f"{_normalize_year(y)}-01-01", "year"
    return None


def find_date_in_text(text: str, head_chars: int = 600, head_lines: int = 5) -> Optional[tuple[str, str]]:
    if not text:
        return None
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][: head_lines]
    for ln in lines:
        parsed = parse_date_str(ln)
        if parsed:
            return parsed
    head = text[:head_chars]
    return parse_date_str(head)


# -----------------------------
# Scripture reference parsing (from notesdb-passages)
# -----------------------------
RANGE_SEP = r"[-–—]{1,2}"


def load_aliases(path: str) -> Dict[str, Tuple[str, str]]:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    rev: Dict[str, Tuple[str, str]] = {}
    for key, aliases in cfg.get("aliases", {}).items():
        vol, book = key.split(":", 1)
        vol = vol.strip()
        book = book.strip()
        for a in aliases:
            norm = normalize_alias(a)
            rev[norm] = (vol, book)
    return rev


def normalize_alias(s: str) -> str:
    s = s.lower()
    s = s.replace("&", " and ").replace("+", " and ")
    s = re.sub(r"[\.·—–\-_/]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def alias_to_pattern(alias: str) -> str:
    out = []
    i = 0
    alias = alias.strip()
    while i < len(alias):
        ch = alias[i]
        if ch.isalnum():
            j = i
            while j < len(alias) and alias[j].isalnum():
                j += 1
            word = re.escape(alias[i:j])
            out.append(f"{word}\\.?")
            i = j
        elif ch in ['&', '+']:
            out.append(r"\s*(?:and|&|\+)\s*")
            while i < len(alias) and alias[i] in ['&', '+']:
                i += 1
        elif ch == ' ':
            out.append(r"\s*")
            while i < len(alias) and alias[i] == ' ':
                i += 1
        elif ch in ['-', '_', '/', '.']:
            out.append(r"\s*")
            i += 1
        else:
            out.append(r"\s*")
            i += 1
    return "".join(out)


def compile_ref_regex_from_aliases(aliases: Dict[str, Tuple[str, str]]) -> re.Pattern:
    alts = []
    for norm_alias in aliases.keys():
        alias_form = norm_alias.replace(" and ", " & ")
        alts.append(alias_to_pattern(alias_form))
    book_group = "(?P<book>(?:" + "|".join(alts) + "))"
    chap = r"\s*(?P<chap>\d{1,3})"
    verses = (
        r"(?::\s*(?P<verses>\d{1,3}(?:\s*" + RANGE_SEP + r"\s*\d{1,3})?(?:\s*,\s*\d{1,3}(?:\s*"
        + RANGE_SEP
        + r"\s*\d{1,3})?)*))?"
    )
    pattern = r"\b" + book_group + chap + verses + r"(?![A-Za-z])"
    return re.compile(pattern, re.IGNORECASE)


@dataclass
class BookKey:
    volume: str
    book: str


def resolve_book(std: sqlite3.Connection, key: BookKey) -> Tuple[int, int]:
    cur = std.execute("SELECT id FROM volume WHERE lower(VolumeName) = lower(?)", (key.volume,))
    vrow = cur.fetchone()
    if not vrow:
        raise RuntimeError(f"Volume not found: {key.volume}")
    vol_id = int(vrow[0])
    cur = std.execute("SELECT id FROM book WHERE fkVolume = ? AND lower(BookName) = lower(?)", (vol_id, key.book))
    brow = cur.fetchone()
    if not brow:
        cur = std.execute("SELECT id FROM book WHERE fkVolume = ? AND lower(ShortTitle) = lower(?)", (vol_id, key.book))
        brow = cur.fetchone()
    if not brow:
        raise RuntimeError(f"Book not found: {key.volume}:{key.book}")
    return vol_id, int(brow[0])


def chapter_bounds(std: sqlite3.Connection, book_id: int, chap_num: str) -> Tuple[int, int]:
    cur = std.execute(
        "SELECT id FROM chapter WHERE fkBook = ? AND ChapterNumber = ?",
        (book_id, str(chap_num)),
    )
    crow = cur.fetchone()
    if not crow:
        raise RuntimeError(f"Chapter not found: book={book_id} chap={chap_num}")
    chap_id = int(crow[0])
    cur = std.execute("SELECT MAX(VerseNumber) FROM verse WHERE fkChapter = ?", (chap_id,))
    vmax = int(cur.fetchone()[0] or 0)
    return chap_id, vmax


def verse_id(std: sqlite3.Connection, chap_id: int, verse_num: int) -> int:
    cur = std.execute("SELECT id FROM verse WHERE fkChapter = ? AND VerseNumber = ?", (chap_id, int(verse_num)))
    vrow = cur.fetchone()
    if not vrow:
        raise RuntimeError(f"Verse not found: chap={chap_id} v={verse_num}")
    return int(vrow[0])


def upsert_passage(notes: sqlite3.Connection, start_id: int, end_id: int, citation: str) -> int:
    notes.execute(
        """
        INSERT INTO passage(start_verse_id, end_verse_id, citation)
        VALUES (?, ?, ?)
        ON CONFLICT(start_verse_id, end_verse_id) DO NOTHING
        """,
        (start_id, end_id, citation),
    )
    cur = notes.execute(
        "SELECT id FROM passage WHERE start_verse_id = ? AND end_verse_id = ?",
        (start_id, end_id),
    )
    return int(cur.fetchone()[0])


def link_note_passage(notes: sqlite3.Connection, note_id: int, passage_id: int) -> None:
    notes.execute(
        "INSERT OR IGNORE INTO note_passage(note_id, passage_id, relation) VALUES (?, ?, 'mentions')",
        (note_id, passage_id),
    )


def make_citation(book_disp: str, chap: int, vranges: List[Tuple[int, int]]) -> str:
    parts: List[str] = []
    for a, b in vranges:
        parts.append(str(a) if a == b else f"{a}–{b}")
    verses = ", ".join(parts)
    return f"{book_disp} {chap}:{verses}" if verses else f"{book_disp} {chap}"


def parse_verses_list(vs: Optional[str]) -> List[Tuple[int, int]]:
    if not vs:
        return []
    out: List[Tuple[int, int]] = []
    for part in re.split(r"\s*,\s*", vs.strip()):
        if not part:
            continue
        m = re.match(rf"^(\d{{1,3}})\s*(?:{RANGE_SEP})\s*(\d{{1,3}})$", part)
        if m:
            a = int(m.group(1)); b = int(m.group(2))
            out.append((min(a, b), max(a, b)))
        else:
            try:
                v = int(part)
                out.append((v, v))
            except ValueError:
                continue
    return out


def parse_parenthetical_after(text: str, end_idx: int) -> List[Tuple[int, int]]:
    tail = text[end_idx : end_idx + 64]
    m = re.match(r"\s*\((?P<inner>\s*\d{1,3}(?:\s*" + RANGE_SEP + r"\s*\d{1,3})?(?:\s*,\s*\d{1,3}(?:\s*" + RANGE_SEP + r"\s*\d{1,3})?)*\s*)\)", tail)
    if not m:
        return []
    inner = m.group("inner")
    return parse_verses_list(inner)


def link_scripture_refs(note_id: int, text: str, notes: sqlite3.Connection, std: sqlite3.Connection, alias_map: Dict[str, Tuple[str, str]]) -> Tuple[int, int]:
    regex = compile_ref_regex_from_aliases(alias_map)
    found = 0
    linked = 0
    s = text or ""
    for m in regex.finditer(s):
        raw_book = (m.group("book") or "").strip()
        chap = int(m.group("chap"))
        verses_str = m.group("verses")
        norm = normalize_alias(raw_book)
        key = alias_map.get(norm)
        if not key:
            continue
        vol, book = key
        try:
            _vol_id, book_id = resolve_book(std, BookKey(vol, book))
            chap_id, maxv = chapter_bounds(std, book_id, chap)
        except Exception:
            continue
        vranges = parse_verses_list(verses_str)
        extra = parse_parenthetical_after(s, m.end())
        if extra:
            if not vranges:
                vranges = extra
            else:
                vranges.extend(extra)
        if not vranges:
            start = verse_id(std, chap_id, 1)
            end = verse_id(std, chap_id, maxv)
            citation = make_citation(book, chap, [])
            pid = upsert_passage(notes, start, end, citation)
            link_note_passage(notes, note_id, pid)
            found += 1; linked += 1
            continue
        for a, b in vranges:
            if a < 1 or b < 1 or a > maxv or b > maxv:
                continue
            try:
                start = verse_id(std, chap_id, a)
                end = verse_id(std, chap_id, b)
            except Exception:
                continue
            citation = make_citation(book, chap, [(a, b)])
            pid = upsert_passage(notes, start, end, citation)
            link_note_passage(notes, note_id, pid)
            found += 1; linked += 1
    return found, linked


# -----------------------------
# DB helpers
# -----------------------------
def open_db(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def apply_schema(conn: sqlite3.Connection, schema_path: Path) -> None:
    sql = schema_path.read_text(encoding="utf-8")
    conn.executescript(sql)


def media_type_for(path: Path) -> str:
    if path.suffix.lower() in {".md"}:
        return "text/markdown"
    if path.suffix.lower() in {".json"}:
        return "application/json"
    mt, _ = mimetypes.guess_type(str(path))
    return mt or "application/octet-stream"


def upsert_inputfile(conn: sqlite3.Connection, path: Path, original_filename: Optional[str] = None) -> int:
    size = path.stat().st_size if path.exists() else None
    conn.execute(
        """
        INSERT INTO inputfile(path, original_filename, size_bytes, media_type)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET
            original_filename=COALESCE(inputfile.original_filename, excluded.original_filename),
            size_bytes=COALESCE(excluded.size_bytes, inputfile.size_bytes),
            media_type=COALESCE(excluded.media_type, inputfile.media_type)
        """,
        (str(path), original_filename or path.name, size, media_type_for(path)),
    )
    cur = conn.execute("SELECT id FROM inputfile WHERE path=?", (str(path),))
    return int(cur.fetchone()[0])


def infer_format_from_path(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext == ".png":
        return "png"
    if ext in {".jpg", ".jpeg"}:
        return "jpeg"
    if ext in {".tif", ".tiff"}:
        return "tiff"
    return None


def upsert_file(conn: sqlite3.Connection, path: Path) -> int:
    fmt = infer_format_from_path(path)
    if not fmt:
        raise RuntimeError(f"unsupported image format: {path}")
    conn.execute(
        """
        INSERT INTO file(path, format)
        VALUES(?, ?)
        ON CONFLICT(path) DO UPDATE SET
            format=excluded.format
        """,
        (str(path), fmt),
    )
    cur = conn.execute("SELECT id FROM file WHERE path=?", (str(path),))
    return int(cur.fetchone()[0])


def insert_note(conn: sqlite3.Connection, content: str) -> int:
    cur = conn.execute("INSERT INTO note(content) VALUES (?)", (content,))
    return int(cur.lastrowid)


def set_note_prev_next(conn: sqlite3.Connection, note_ids: List[int]) -> None:
    for i, nid in enumerate(note_ids):
        prev_id = note_ids[i - 1] if i > 0 else None
        next_id = note_ids[i + 1] if i + 1 < len(note_ids) else None
        conn.execute(
            "UPDATE note SET prev_note_id=?, next_note_id=? WHERE id=?",
            (prev_id, next_id, nid),
        )


def link_note_file(conn: sqlite3.Connection, note_id: int, file_id: int, page_order: Optional[int]) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO note_file(note_id, file_id, page_order) VALUES (?, ?, ?)",
        (note_id, file_id, page_order),
    )


def link_note_inputfile(conn: sqlite3.Connection, note_id: int, inputfile_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO note_inputfile(note_id, inputfile_id) VALUES (?, ?)",
        (note_id, inputfile_id),
    )


def set_note_date(conn: sqlite3.Connection, note_id: int, text: str, fallback_name: Optional[str]) -> None:
    dprec = find_date_in_text(text)
    if not dprec and fallback_name:
        dprec = parse_date_str(fallback_name)
    if dprec:
        d, prec = dprec
        conn.execute(
            "UPDATE note SET date_created=?, date_created_precision=? WHERE id=?",
            (d, prec, note_id),
        )


# -----------------------------
# Sources: OCR/txt/Images
# -----------------------------
def process_pdf_batch_root(conn: sqlite3.Connection, ocr_root: Path, images_dir: Path, std_db: str, aliases_path: str) -> Tuple[int, int]:
    manifest = None
    moved = ocr_root / "moved_images.json"
    if (ocr_root / "manifest.json").exists():
        manifest = json.loads((ocr_root / "manifest.json").read_text(encoding="utf-8"))
    elif moved.exists():
        # Build a minimal manifest-compatible structure
        data = json.loads(moved.read_text(encoding="utf-8"))
        manifest = {"images": data.get("images", []), "prefix": data.get("prefix"), "sha": data.get("sha")}
    meta = None
    if (ocr_root / "meta.json").exists():
        try:
            meta = json.loads((ocr_root / "meta.json").read_text(encoding="utf-8"))
        except Exception:
            meta = None

    source_pdf = None
    if meta and meta.get("source"):
        source_pdf = Path(meta["source"]) if isinstance(meta["source"], str) else None
    # txt files live under pages/ as page-xxxx.txt
    pages_dir = ocr_root / "pages"
    txt_pages = sorted(pages_dir.glob("page-*.txt"))
    if not txt_pages:
        return 0, 0

    # Upsert inputfile for the source PDF if known
    inputfile_id = None
    if source_pdf and str(source_pdf).strip():
        try:
            inputfile_id = upsert_inputfile(conn, source_pdf, original_filename=source_pdf.name)
        except Exception:
            inputfile_id = None

    # Prepare scripture linking
    alias_map = load_aliases(aliases_path) if aliases_path and Path(aliases_path).exists() else {}
    std_conn = sqlite3.connect(str(DEFAULT_STD_DB)) if std_db and Path(std_db).exists() else None

    created_notes: List[int] = []
    with conn:
        for idx, txt_path in enumerate(txt_pages, start=1):
            text = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            nid = insert_note(conn, text)
            created_notes.append(nid)
            # Link images by order via manifest images list if available, else by prefix pattern
            file_id = None
            if manifest and manifest.get("images"):
                try:
                    entry = manifest["images"][idx - 1]
                    img_dest = entry.get("dest") if isinstance(entry, dict) else None
                    if img_dest:
                        img_path = Path(img_dest)
                        if not img_path.is_absolute():
                            img_path = images_dir / Path(img_dest).name
                        file_id = upsert_file(conn, img_path)
                except Exception:
                    file_id = None
            if file_id is None:
                # Derive from sha prefix in ocr_root name or from png alongside txt
                # First, try a sibling PNG
                png_guess = txt_path.with_suffix(".png")
                if png_guess.exists():
                    file_id = upsert_file(conn, png_guess)
                else:
                    # Attempt to find page images that match sha prefix
                    sha = ocr_root.name
                    candidates = sorted(images_dir.glob(f"*{sha}*p{idx:04d}.png"))
                    if candidates:
                        file_id = upsert_file(conn, candidates[0])
            if file_id is not None:
                link_note_file(conn, nid, file_id, page_order=idx)
            if inputfile_id is not None:
                link_note_inputfile(conn, nid, inputfile_id)
            # Set date (from note text; fallback to source file name)
            set_note_date(conn, nid, text, source_pdf.name if source_pdf else None)
            # Scripture refs
            if std_conn is not None and alias_map:
                try:
                    link_scripture_refs(nid, text, conn, std_conn, alias_map)
                except Exception:
                    pass
    # Chain prev/next for this PDF
    set_note_prev_next(conn, created_notes)
    if std_conn is not None:
        std_conn.close()
    return len(created_notes), 1


def rebuild_from_ocr_dir(conn: sqlite3.Connection, ocr_dir: Path, images_dir: Path, std_db: str, aliases_path: str) -> Tuple[int, int]:
    total_notes = 0
    batches = 0
    if not ocr_dir.exists():
        return 0, 0
    for root in sorted(ocr_dir.iterdir()):
        if not root.is_dir():
            continue
        n, b = process_pdf_batch_root(conn, root, images_dir, std_db, aliases_path)
        total_notes += n
        batches += b
    return total_notes, batches


def rebuild_from_txt_dir(conn: sqlite3.Connection, txt_dir: Path, images_dir: Path, std_db: str, aliases_path: str) -> Tuple[int, int]:
    total_notes = 0
    batches = 0
    if not txt_dir.exists():
        return 0, 0
    for root in sorted(txt_dir.iterdir()):
        if root.is_dir():
            # Treat each subdir as a PDF batch with page-*.txt and optional manifest.json
            n, b = process_pdf_batch_root(conn, root, images_dir, std_db, aliases_path)
            total_notes += n
            batches += b
        elif root.suffix.lower() == ".txt":
            # Standalone text file becomes a single note
            text = root.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            with conn:
                nid = insert_note(conn, text)
                # provenance
                try:
                    input_id = upsert_inputfile(conn, root, original_filename=root.name)
                    link_note_inputfile(conn, nid, input_id)
                except Exception:
                    pass
                set_note_date(conn, nid, text, root.name)
                # scripture
                if Path(std_db).exists() and Path(aliases_path).exists():
                    try:
                        std_conn = sqlite3.connect(str(std_db))
                        alias_map = load_aliases(aliases_path)
                        link_scripture_refs(nid, text, conn, std_conn, alias_map)
                        std_conn.close()
                    except Exception:
                        pass
            total_notes += 1
            batches += 1
    return total_notes, batches


def rebuild_from_images(conn: sqlite3.Connection, images_dir: Path, std_db: str, aliases_path: str) -> Tuple[int, int]:
    total_notes = 0
    processed = 0
    if not images_dir.exists():
        return 0, 0
    # For each .txt next to an image, create a note and link to that image
    for txt_path in sorted(images_dir.glob("*.txt")):
        stem = txt_path.stem
        img = None
        for ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"):
            cand = images_dir / f"{stem}{ext}"
            if cand.exists():
                img = cand
                break
        text = txt_path.read_text(encoding="utf-8", errors="ignore").strip()
        if not text:
            continue
        with conn:
            nid = insert_note(conn, text)
            if img and img.exists():
                try:
                    fid = upsert_file(conn, img)
                    link_note_file(conn, nid, fid, page_order=None)
                except Exception:
                    pass
            # provenance: use the image itself as inputfile if available; otherwise the txt file
            try:
                if img and img.exists():
                    iid = upsert_inputfile(conn, img, original_filename=img.name)
                    link_note_inputfile(conn, nid, iid)
                else:
                    iid = upsert_inputfile(conn, txt_path, original_filename=txt_path.name)
                    link_note_inputfile(conn, nid, iid)
            except Exception:
                pass
            set_note_date(conn, nid, text, (img.name if img else txt_path.name))
            if Path(std_db).exists() and Path(aliases_path).exists():
                try:
                    std_conn = sqlite3.connect(str(std_db))
                    alias_map = load_aliases(aliases_path)
                    link_scripture_refs(nid, text, conn, std_conn, alias_map)
                    std_conn.close()
                except Exception:
                    pass
        total_notes += 1
        processed += 1
    return total_notes, processed


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild notes.db from /data/txt, /data/ocr, and /data/images artifacts")
    ap.add_argument("--db", default=DEFAULT_NOTES_DB)
    ap.add_argument("--schema", default=str(DEFAULT_SCHEMA))
    ap.add_argument("--txt-dir", default=str(DEFAULT_TXT_DIR))
    ap.add_argument("--ocr-dir", default=str(DEFAULT_OCR_DIR))
    ap.add_argument("--images-dir", default=str(DEFAULT_IMAGES_DIR))
    ap.add_argument("--std-db", default=DEFAULT_STD_DB)
    ap.add_argument("--aliases", default=DEFAULT_ALIASES)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(open_db(db_path)) as conn:
        # Reset DB by applying schema (CREATE IF NOT EXISTS; assumes a new file or compatible schema)
        apply_schema(conn, Path(args.schema))
        notes = 0
        groups = 0
        # PDFs: look under /data/txt and /data/ocr
        n1, b1 = rebuild_from_txt_dir(conn, Path(args.txt_dir), Path(args.images_dir), args.std_db, args.aliases)
        notes += n1; groups += b1
        n2, b2 = rebuild_from_ocr_dir(conn, Path(args.ocr_dir), Path(args.images_dir), args.std_db, args.aliases)
        notes += n2; groups += b2
        # Single images (and any stray .txt in images dir)
        n3, b3 = rebuild_from_images(conn, Path(args.images_dir), args.std_db, args.aliases)
        notes += n3; groups += b3
    print(f"[rebuild_database] notes={notes} groups={groups}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

