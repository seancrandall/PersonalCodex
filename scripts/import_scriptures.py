#!/usr/bin/env python3
"""
Import scriptures HTML into the Standard Works SQLite schema.

Assumptions (customize via flags):
- Directory layout: src/scripturedb/scriptures/<Volume>/<Book>/*.html
- Chapter HTML contains verse markers as <sup>digits</sup> or similar; if none
  found, treat each non-empty <p> as a sequentially numbered verse.
- Front matter (e.g., Introduction, Witnesses) is imported as chapters with a
  textual ChapterNumber (e.g., "Introduction").

Usage examples:
  python scripts/import_scriptures.py \
    --root src/scripturedb/scriptures \
    --db volumes/scripdb/standardworks.db

Options:
  --clear-chapter   If a chapter exists, delete and reimport its verses.
  --dry-run         Parse and report, but do not write to the DB.
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional, Tuple


try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except Exception as e:  # pragma: no cover - advisory when bs4 missing
    raise SystemExit(
        "This script requires BeautifulSoup4. Install with: pip install beautifulsoup4"
    )


@dataclass
class ParsedChapter:
    chapter_id_text: str  # chapter identifier as text (e.g., "1", "Introduction")
    heading: Optional[str]
    verses: List[Tuple[int, str]]  # (VerseNumber, VerseContent)


def normalize_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def load_volume_book_maps(conn: sqlite3.Connection) -> Tuple[Dict[str, int], Dict[Tuple[int, str], int]]:
    vol_map: Dict[str, int] = {}
    for vol_id, vol_name in conn.execute("SELECT id, VolumeName FROM volume"):
        vol_map[normalize_key(vol_name)] = int(vol_id)

    book_map: Dict[Tuple[int, str], int] = {}
    for book_id, fk_vol, book_name in conn.execute(
        "SELECT id, fkVolume, BookName FROM book"
    ):
        book_map[(int(fk_vol), normalize_key(book_name))] = int(book_id)

    return vol_map, book_map


def ensure_volume_book(
    conn: sqlite3.Connection, vol_map: Dict[str, int], book_map: Dict[Tuple[int, str], int],
    volume_name: str, book_name: str
) -> Tuple[int, int]:
    vkey = normalize_key(volume_name)
    vol_id = vol_map.get(vkey)
    if vol_id is None:
        conn.execute("INSERT INTO volume(VolumeName) VALUES (?)", (volume_name,))
        vol_id = conn.execute(
            "SELECT id FROM volume WHERE VolumeName=?", (volume_name,)
        ).fetchone()[0]
        vol_map[vkey] = int(vol_id)

    bkey = (int(vol_id), normalize_key(book_name))
    bid = book_map.get(bkey)
    if bid is None:
        conn.execute(
            "INSERT INTO book(fkVolume, BookName) VALUES (?, ?)", (vol_id, book_name)
        )
        bid = conn.execute(
            "SELECT id FROM book WHERE fkVolume=? AND BookName=?",
            (vol_id, book_name),
        ).fetchone()[0]
        book_map[bkey] = int(bid)
    return int(vol_id), int(bid)


def extract_book_long_title(soup: BeautifulSoup) -> Optional[str]:
    # Long title typically in the first h1 before the verses
    verses = soup.select("p.verse")
    first_verse = verses[0] if verses else None
    if first_verse:
        for el in first_verse.find_all_previous("h1"):
            text = el.get_text(" ", strip=True)
            if text:
                return text
    h1 = soup.find("h1")
    if h1:
        t = h1.get_text(" ", strip=True)
        if t:
            return t
    return None


def extract_chapter_heading(soup: BeautifulSoup) -> Optional[str]:
    # LDS edition provides a study-summary per chapter
    ss = soup.select_one(".study-summary")
    if ss:
        t = ss.get_text(" ", strip=True)
        if t:
            return t
    # Fallback: subtitle near header
    sub = soup.select_one(".subtitle")
    if sub:
        t = sub.get_text(" ", strip=True)
        if t:
            return t
    return None


def derive_chapter_id_text(path: Path, soup: BeautifulSoup) -> str:
    base = path.stem
    # Known front-matter patterns
    fm_map = {
        "introduction": "Introduction",
        "witness": "Witnesses",
        "testimonyofthreewitnesses": "Testimony of Three Witnesses",
        "testimonyofeightwitnesses": "Testimony of Eight Witnesses",
        "preface": "Preface",
        "foreword": "Foreword",
    }
    key = normalize_key(base)
    for k, label in fm_map.items():
        if k in key:
            return label

    # Try to find a number in filename, heading, or title
    for source in (base, extract_book_long_title(soup) or "", getattr(soup.title, "string", "") or ""):
        m = re.search(r"\b(\d+)\b", source)
        if m:
            return m.group(1)

    # Fallback: Title-case filename as a textual chapter id
    return re.sub(r"[_-]+", " ", base).strip().title()


def _text_of(node: Tag | NavigableString) -> str:
    if isinstance(node, NavigableString):
        return str(node)
    elif isinstance(node, Tag):
        return node.get_text(" ")
    return ""


def normalize_text(s: str) -> str:
    # Fix common mojibake and punctuation; collapse whitespace; trim spaces before punctuation
    replacements = {
        "â\x80\x94": "—",  # em dash
        "â\x80\x93": "–",  # en dash
        "â\x80\x98": "‘",
        "â\x80\x99": "’",
        "â\x80\x9c": "“",
        "â\x80\x9d": "”",
        "â\x80\xa6": "…",
        "Â ": " ",  # non-breaking space artifact
        "Â": " ",
        "â": "",
    }
    for k, v in replacements.items():
        s = s.replace(k, v)
    # Replace 3+ dots with ellipsis
    s = re.sub(r"\.\.\.\.+", "…", s)
    s = re.sub(r"\.\.\.", "…", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s)
    # Remove space before punctuation
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    return s.strip()

def extract_verses(soup: BeautifulSoup) -> List[Tuple[int, str]]:
    """Extract (VerseNumber, VerseContent) pairs.

    Strategy:
      - If we detect <sup>digit</sup> markers, split content accordingly across paragraphs.
      - Else, treat each non-empty <p> as a verse, numbered sequentially.
    """
    # Scope to likely content paragraphs:
    # - Scripture chapters: <p class="verse"> with a nested <span class="verse-number">N</span>
    # - Front matter/intros: <p data-aid="..."> blocks in the main content
    paragraphs = soup.select("p.verse, p[data-aid]")
    verses: List[Tuple[int, str]] = []
    found_numeric_markers = False

    for p in paragraphs:
        current_num: Optional[int] = None
        buffer: List[str] = []

        for child in p.children:
            if isinstance(child, Tag):
                # Look for numeric verse markers in <sup> or <span> etc.
                if child.name in {"sup", "span"}:
                    text = child.get_text(strip=True)
                    if text.isdigit():
                        found_numeric_markers = True
                        # Flush previous verse if present
                        if current_num is not None and buffer:
                            verses.append((current_num, " ".join(buffer).strip()))
                        try:
                            current_num = int(text)
                        except ValueError:
                            # Skip non-integer markers
                            current_num = None
                        buffer = []
                        continue
                buffer.append(child.get_text(" "))
            elif isinstance(child, NavigableString):
                buffer.append(str(child))

        # Flush at end of paragraph
        if current_num is not None and buffer:
            verses.append((current_num, " ".join(buffer).strip()))

    if verses and found_numeric_markers:
        # Deduplicate by verse number (keep first occurrence)
        seen: set[int] = set()
        unique: List[Tuple[int, str]] = []
        for n, t in verses:
            if n not in seen:
                unique.append((n, normalize_text(t)))
                seen.add(n)
        return unique

    # Fallback: treat each <p> as a verse
    fallback: List[Tuple[int, str]] = []
    n = 1
    for p in paragraphs:
        txt = p.get_text(" ", strip=True)
        if txt:
            fallback.append((n, normalize_text(txt)))
            n += 1
    return fallback


def parse_chapter_file(path: Path) -> ParsedChapter:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    heading = extract_chapter_heading(soup)
    chap_id = derive_chapter_id_text(path, soup)
    verses = extract_verses(soup)
    return ParsedChapter(chapter_id_text=chap_id, heading=heading, verses=verses)


def is_html_file(p: Path) -> bool:
    return p.is_file() and p.suffix.lower() in {".html", ".htm"}


def import_book_dir(
    conn: sqlite3.Connection,
    vol_map: Dict[str, int],
    book_map: Dict[Tuple[int, str], int],
    volume_name: str,
    book_name: str,
    book_dir: Path,
    clear_chapter: bool,
    dry_run: bool,
) -> None:
    vol_id, book_id = ensure_volume_book(conn, vol_map, book_map, volume_name, book_name)

    chapter_files = sorted([p for p in book_dir.iterate()]) if hasattr(book_dir, 'iterate') else sorted(book_dir.glob("*.htm*"))
    # If nested, also consider subdirectories
    if not chapter_files:
        chapter_files = sorted(book_dir.rglob("*.htm*"))

    for chapter_file in chapter_files:
        if not is_html_file(chapter_file):
            continue
        parsed = parse_chapter_file(chapter_file)

        # Upsert chapter
        row = conn.execute(
            "SELECT id FROM chapter WHERE fkBook=? AND ChapterNumber=?",
            (book_id, parsed.chapter_id_text),
        ).fetchone()
        if row:
            chapter_id = int(row[0])
            if clear_chapter and not dry_run:
                conn.execute("DELETE FROM verse WHERE fkChapter=?", (chapter_id,))
                conn.execute(
                    "UPDATE chapter SET ChapterHeading=? WHERE id=?",
                    (parsed.heading, chapter_id),
                )
        else:
            if dry_run:
                chapter_id = -1
            else:
                conn.execute(
                    "INSERT INTO chapter(fkBook, ChapterNumber, ChapterHeading) VALUES (?,?,?)",
                    (book_id, parsed.chapter_id_text, parsed.heading),
                )
                chapter_id = int(
                    conn.execute("SELECT last_insert_rowid();").fetchone()[0]
                )

        # Insert verses
        if not dry_run:
            for vn, vt in parsed.verses:
                conn.execute(
                    "INSERT OR REPLACE INTO verse(fkChapter, VerseNumber, VerseContent) VALUES (?,?,?)",
                    (chapter_id, vn, vt),
                )

        print(
            f"Imported {volume_name} / {book_name} / {parsed.chapter_id_text}: {len(parsed.verses)} verses"
        )


# -------------------- Flat filename mapping --------------------

# Volume code -> full name
VOLUME_MAP: Dict[str, str] = {
    "ot": "Old Testament",
    "nt": "New Testament",
    "bofm": "Book of Mormon",
    "dc-testament": "Doctrine and Covenants",
    "pgp": "Pearl of Great Price",
}

# Book codes per volume -> full book name
BOOK_MAP: Dict[str, Dict[str, str]] = {
    "ot": {
        "gen": "Genesis", "ex": "Exodus", "lev": "Leviticus", "num": "Numbers", "deut": "Deuteronomy",
        "josh": "Joshua", "judg": "Judges", "ruth": "Ruth",
        "1-sam": "1 Samuel", "2-sam": "2 Samuel", "1-kgs": "1 Kings", "2-kgs": "2 Kings",
        "1-chr": "1 Chronicles", "2-chr": "2 Chronicles",
        "ezra": "Ezra", "neh": "Nehemiah", "esth": "Esther", "job": "Job", "ps": "Psalms",
        "prov": "Proverbs", "eccl": "Ecclesiastes", "song": "Song of Solomon",
        "isa": "Isaiah", "jer": "Jeremiah", "lam": "Lamentations", "ezek": "Ezekiel", "dan": "Daniel",
        "hosea": "Hosea", "joel": "Joel", "amos": "Amos", "obad": "Obadiah", "jonah": "Jonah",
        "micah": "Micah", "nahum": "Nahum", "hab": "Habakkuk", "zeph": "Zephaniah", "hag": "Haggai",
        "zech": "Zechariah", "mal": "Malachi",
    },
    "nt": {
        "matt": "Matthew", "mark": "Mark", "luke": "Luke", "john": "John", "acts": "Acts",
        "rom": "Romans", "1-cor": "1 Corinthians", "2-cor": "2 Corinthians",
        "gal": "Galatians", "eph": "Ephesians", "phil": "Philippians", "philip": "Philippians", "col": "Colossians",
        "1-thes": "1 Thessalonians", "2-thes": "2 Thessalonians", "1-tim": "1 Timothy", "2-tim": "2 Timothy",
        "titus": "Titus", "philem": "Philemon", "heb": "Hebrews", "james": "James",
        "1-pet": "1 Peter", "2-pet": "2 Peter", "1-jn": "1 John", "2-jn": "2 John", "3-jn": "3 John",
        "jude": "Jude", "rev": "Revelation",
    },
    "bofm": {
        "1-ne": "1 Nephi", "2-ne": "2 Nephi", "jacob": "Jacob", "enos": "Enos", "jarom": "Jarom",
        "omni": "Omni", "w-of-m": "Words of Mormon", "mosiah": "Mosiah", "alma": "Alma", "hel": "Helaman",
        "3-ne": "3 Nephi", "4-ne": "4 Nephi", "morm": "Mormon", "ether": "Ether", "moro": "Moroni",
    },
    "dc-testament": {
        "dc": "Sections", "od": "Official Declarations",
    },
    "pgp": {
        "moses": "Moses", "abr": "Abraham", "js-m": "Joseph Smith—Matthew", "js-h": "Joseph Smith—History",
        "a-of-f": "Articles of Faith",
    },
}

FRONT_MATTER_LABELS: Dict[str, str] = {
    # general
    "title-page": "Title Page", "introduction": "Introduction", "preface": "Preface", "foreword": "Foreword",
    # Book of Mormon specifics
    "bofm-title": "Title Page of the Book of Mormon",
    "three": "Testimony of Three Witnesses",
    "eight": "Testimony of Eight Witnesses",
    "js": "Testimony of the Prophet Joseph Smith",
    "explanation": "Brief Explanation about the Book of Mormon",
    "illustrations": "Illustrations",
    # D&C
    "chron-order": "Chronological Order of Contents",
}


def parse_filename_meta(path: Path) -> Optional[Tuple[str, str, str]]:
    """Infer (volume_name, book_name, chapter_id_text) from a flat filename.

    Returns None if the file should be skipped (e.g., contents pages).
    """
    name = path.stem  # without extension
    m = re.match(r"^(ot|nt|bofm|dc-testament|pgp)_(.+)$", name)
    if not m:
        return None
    vol_code, rest = m.group(1), m.group(2)

    # Skip JSON handled elsewhere; here only html/htm reach us
    # Filter known non-content suffixes
    if rest.endswith("__contents"):
        return None
    # Skip references, pronunciation guides, and facsimiles
    if any(x in rest for x in ("reference", "pronunciation", "fac-")):
        return None

    # Split book/frontmatter + optional chapter
    # prefer last underscore as chapter separator
    chap = None
    if "_" in rest:
        base, last = rest.rsplit("_", 1)
        if last.isdigit():
            chap = last
            code = base
        else:
            code = rest
    else:
        code = rest

    volume_name = VOLUME_MAP.get(vol_code, vol_code)

    # Front matter?
    if code in FRONT_MATTER_LABELS and chap is None:
        # Attach to a reasonable book for hierarchy; use a synthetic book per volume
        book_name = {
            "ot": "Front Matter",
            "nt": "Front Matter",
            "bofm": "Introduction and Witnesses",
            "dc-testament": "Front Matter",
            "pgp": "Front Matter",
        }.get(vol_code, "Front Matter")
        chapter_text = FRONT_MATTER_LABELS[code]
        return volume_name, book_name, chapter_text

    # Normal book
    book_name = BOOK_MAP.get(vol_code, {}).get(code)
    if not book_name:
        # Unknown code; skip indexes or references
        return None
    # If there's no explicit chapter in filename, skip landing pages to avoid duplicates
    if chap is None:
        return None
    chapter_text = chap
    return volume_name, book_name, chapter_text


def import_by_filenames(
    conn: sqlite3.Connection,
    vol_map: Dict[str, int],
    book_map: Dict[Tuple[int, str], int],
    files: List[Path],
    clear_chapter: bool,
    dry_run: bool,
) -> None:
    for f in files:
        if not is_html_file(f):
            continue
        meta = parse_filename_meta(f)
        if not meta:
            continue
        volume_name, book_name, chap_text = meta
        vol_id, book_id = ensure_volume_book(conn, vol_map, book_map, volume_name, book_name)
        parsed = parse_chapter_file(f)
        # Override derived chapter id with filename-derived chap_text for consistency
        parsed.chapter_id_text = chap_text

        # Upsert chapter
        row = conn.execute(
            "SELECT id FROM chapter WHERE fkBook=? AND ChapterNumber=?",
            (book_id, parsed.chapter_id_text),
        ).fetchone()
        if row:
            chapter_id = int(row[0])
            if clear_chapter and not dry_run:
                conn.execute("DELETE FROM verse WHERE fkChapter=?", (chapter_id,))
                conn.execute(
                    "UPDATE chapter SET ChapterHeading=? WHERE id=?",
                    (parsed.heading, chapter_id),
                )
        else:
            if dry_run:
                chapter_id = -1
            else:
                conn.execute(
                    "INSERT INTO chapter(fkBook, ChapterNumber, ChapterHeading) VALUES (?,?,?)",
                    (book_id, parsed.chapter_id_text, parsed.heading),
                )
                chapter_id = int(conn.execute("SELECT last_insert_rowid();").fetchone()[0])

        if not dry_run:
            for vn, vt in parsed.verses:
                conn.execute(
                    "INSERT OR REPLACE INTO verse(fkChapter, VerseNumber, VerseContent) VALUES (?,?,?)",
                    (chapter_id, vn, vt),
                )

        print(
            f"Imported {volume_name} / {book_name} / {parsed.chapter_id_text}: {len(parsed.verses)} verses from {f.name}"
        )


def update_book_metadata_from_first_chapters(
    conn: sqlite3.Connection, root: Path
) -> None:
    # For each known book code, if chapter 1 file exists, extract LongTitle and optional BookHeading
    for vol_code, books in BOOK_MAP.items():
        volume_name = VOLUME_MAP.get(vol_code, vol_code)
        for code, book_name in books.items():
            chap1 = root / f"{vol_code}_{code}_1.html"
            if not chap1.exists():
                continue
            soup = BeautifulSoup(chap1.read_text(encoding="utf-8", errors="ignore"), "html.parser")
            long_title = extract_book_long_title(soup)
            # Prefer a concise book heading: use .subtitle if present, else the first non-trivial paragraph before first verse
            book_heading = None
            sub = soup.select_one(".subtitle")
            if sub:
                txt = sub.get_text(" ", strip=True)
                if txt:
                    book_heading = txt
            # If no explicit subtitle, leave BookHeading null (not all books have one)

            # Update DB
            # ShortTitle: prefer our canonical BookName (mapped); LongTitle as parsed; BookHeading optional
            conn.execute(
                """
                UPDATE book
                SET ShortTitle = COALESCE(ShortTitle, ?),
                    LongTitle = COALESCE(?, LongTitle),
                    BookHeading = COALESCE(?, BookHeading)
                WHERE id IN (
                    SELECT b.id FROM book b JOIN volume v ON v.id=b.fkVolume
                    WHERE v.VolumeName=? AND b.BookName=?
                )
                """,
                (book_name, long_title, book_heading, volume_name, book_name),
            )


def discover_and_import(
    conn: sqlite3.Connection, root: Path, clear_chapter: bool, dry_run: bool
) -> None:
    vol_map, book_map = load_volume_book_maps(conn)

    dirs = [p for p in root.iterdir() if p.is_dir()]
    files = [p for p in root.iterdir() if p.is_file() and is_html_file(p)]

    if files and not dirs:
        # Flat layout: parse by filename mapping
        import_by_filenames(conn, vol_map, book_map, sorted(files), clear_chapter, dry_run)
        return

    # Directory layout fallback (volume/book)
    # Build reverse maps for flexible directory name matching
    vol_by_key = {normalize_key(name): (name, vid) for name, vid in [
        (row[0], row[1]) for row in conn.execute("SELECT VolumeName, id FROM volume")
    ]}

    # Walk volumes
    for volume_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        vkey = normalize_key(volume_dir.name)
        # Match by normalized name against known volumes; else use raw dir name
        volume_name = next(
            (name for key, (name, _vid) in vol_by_key.items() if key == vkey),
            volume_dir.name.replace("_", " ").replace("-", " "),
        )

        # Walk books
        for book_dir in sorted([p for p in volume_dir.iterdir() if p.is_dir()]):
            book_name_guess = book_dir.name.replace("_", " ").replace("-", " ").strip()
            import_book_dir(
                conn,
                vol_map,
                book_map,
                volume_name,
                book_name_guess,
                book_dir,
                clear_chapter,
                dry_run,
            )


def main() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    default_db = os.environ.get(
        "STANDARD_WORKS_DB",
        str(repo_root / "volumes" / "scripdb" / "standardworks.db"),
    )

    parser = argparse.ArgumentParser(description="Import scriptures HTML into SQLite DB")
    parser.add_argument("--db", type=Path, default=Path(default_db))
    parser.add_argument("--root", type=Path, default=repo_root / "src" / "scripturedb" / "scriptures")
    parser.add_argument("--clear-chapter", action="store_true", help="Delete existing verses for a chapter before insert")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not args.root.exists():
        raise SystemExit(f"Scriptures root not found: {args.root}")

    args.db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.db) as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        # Update book metadata from first chapters (long/short titles and book headings)
        update_book_metadata_from_first_chapters(conn, args.root)
        discover_and_import(conn, args.root, args.clear_chapter, args.dry_run)
        conn.commit()


if __name__ == "__main__":
    main()
