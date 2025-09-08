# PersonalCodex
A self-hosted, containerized infrastructure for creating searchable scripture study notes and journals

## Getting Started (Docker)
- Copy `.env.example` to `.env` and adjust paths if needed.
- Start the stack (CPU): `docker compose up --build`
  - API: `http://localhost:8000` (docs at `/docs`)
  - Web: `http://localhost:3000`
- GPU default: `docker compose up --build` (requests GPU if available)
- CPU override: `docker compose -f docker-compose.yml -f docker-compose.cpu.yml up --build`
- Data and models live under `./volumes` on host, mounted at `/data` in containers.

## Project Goals & Scope
- Provide a self-hosted web UI to review handwritten scripture notes and general journals, with fast search, tagging, and filtering.
- Consolidate notes from scans (paper → PDFs/images) and existing text files into a single, queryable notes store.
- Correlate notes to the scriptures (Standard Works) with robust cross-references (book/chapter/verse), backlinks, and citations.
- Enable OCR for scanned documents, emitting per-page JSON and plain text with confidence and bounding boxes for future footnotes/citations.
- Support full‑text search across notes and scriptures, plus tags, collections, and simple metadata (dates, sources, notebooks).
- Keep data local-first and private by default; avoid external services. All runtime is containerized via Docker Compose.

## Standard Works DB (Scriptures)

The `scripts/` tools import the LDS Standard Works into a SQLite DB and normalize text.

Quick start
- Prereq: Python 3.11+ and `pip install beautifulsoup4`.
- Run the full pipeline:
  - `make pipeline`

Make targets
- `make init-db` — create the DB and apply schema.
- `make seed` — seed volumes and books.
- `make import` — parse HTML from `src/scripturedb/scriptures` and load chapters/verses (with headings).
- `make normalize` — fix punctuation/whitespace in verses and headings.
- `make summary` — print counts by volume.
- `make check` — verify normalization (used by CI).
- `make clean-db` — remove the DB file.

Config
- DB path: set `DB` (default `volumes/scripdb/standardworks.db`).
- HTML root: set `ROOT` (default `src/scripturedb/scriptures`).

Examples
- `make import ROOT=/absolute/path/to/html`
- `make pipeline DB=/tmp/standardworks.db`

## Notes DB (Scans + Notes)

The notes database stores scanned page files, notes, OCR blocks with full‑text search, tags, cross‑links, passages, and embeddings.

Schema
- Location: `src/notesdb/schema.sql`
- DB file: `volumes/notesdb/notes.db` (kept local; ignored by Git)

Make targets
- `make notesdb` — build `volumes/notesdb/notes.db` from the schema.
- `make validate-notesdb` — attach `volumes/scripdb/standardworks.db` and validate passage verse IDs.
- `make fill-citations` — auto‑fill missing `passage.citation` labels (e.g., `1 Nephi 3:7–9`).
- `make clean-notesdb` — remove the notes DB.

Manual build (without Make)
- `sqlite3 volumes/notesdb/notes.db < src/notesdb/schema.sql`
- Then you can run `python scripts/validate_notes_passages.py --notes-db volumes/notesdb/notes.db --std-db volumes/scripdb/standardworks.db [--fill-citations]`.

Notes
- Personal data under `volumes/*` is ignored by Git except `volumes/bin/` and `volumes/scripdb/`.
- Passage verse IDs reference `standardworks.db`; validation is done by attaching that DB during checks.

Helper CLI
- `volumes/bin/notesdb-rebuild.sh` — rebuilds the notes DB from schema and validates passages.
  - Usage: `volumes/bin/notesdb-rebuild.sh [--fill] [--dry-run] [--notes-db PATH] [--schema PATH] [--std-db PATH]`
  - Examples:
    - Rebuild + validate: `volumes/bin/notesdb-rebuild.sh`
    - Rebuild + validate + fill citations: `volumes/bin/notesdb-rebuild.sh --fill`
    - Preview citation fills only: `volumes/bin/notesdb-rebuild.sh --fill --dry-run`
