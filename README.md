# PersonalCodex
A self-hosted, containerized infrastructure for creating searchable scripture study notes and journals

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
