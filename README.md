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

Linked pages and migration
- Linked navigation: image pages (note_file) now support `prev_file_id` and `next_file_id`. Transcribed pages are stored in a new `transcribed_page` table with `prev_id`/`next_id`.
- Migrate existing DB: `make migrate-notesdb-links`
- Rebuild pointers from page_order: `make rebuild-page-links`
  - Advanced: `python scripts/rebuild_page_links.py --db volumes/notesdb/notes.db --only-missing --dry-run`
- Mark files fully processed (skip on ingest):
  - Mark any file with OCR artifacts: `make mark-processed-ocr`
  - Or:
    - By paths: `python scripts/mark_files_processed.py --db volumes/notesdb/notes.db --paths /data/images/a.png`
    - By ids: `python scripts/mark_files_processed.py --db volumes/notesdb/notes.db --ids 1 2 3`
    - Unset flag: add `--unset`

Manual build (without Make)
- `sqlite3 volumes/notesdb/notes.db < src/notesdb/schema.sql`
- Then you can run `python scripts/validate_notes_passages.py --notes-db volumes/notesdb/notes.db --std-db volumes/scripdb/standardworks.db [--fill-citations]`.

Notes
- Personal data under `volumes/*` is ignored by Git except `volumes/bin/` and `volumes/scripdb/`.
- Passage verse IDs reference `standardworks.db`; validation is done by attaching that DB during checks.
 - Ingestion should prefer files where `fully_processed = 0` and update pointers as it loads pages. The rebuild script can fix up older records.

## Troubleshooting: DNS/Networking in CUDA/PyTorch Builds

CUDA and PyTorch base images can hit DNS/apt flakiness on Fedora/systemd‑resolved hosts. Use both host and container fixes:

- Docker daemon DNS (host):
  - Set nameservers in `/etc/docker/daemon.json`, then restart Docker:
    - `{ "dns": ["<router>", "1.1.1.1", "8.8.8.8"], "dns-opts": ["edns0"], "dns-search": [] }`
  - Configure BuildKit DNS in `/etc/buildkit/buildkitd.toml`:
    - `[dns] nameservers=["<router>", "1.1.1.1", "8.8.8.8"], options=["edns0"], searchDomains=[]`

- Inside Dockerfiles (container level):
  - Wrap apt/pip in `RUN --network=host <<'SH' ... SH`.
  - Before `apt-get update`, temporarily disable NVIDIA/CUDA lists and force IPv4 + retries:
    - Move `/etc/apt/sources.list.d/*cuda*.list` and `*nvidia*.list` aside; add `/etc/apt/apt.conf.d/99-retries-ipv4` with `Acquire::Retries "3"; Acquire::ForceIPv4 "true";`.
  - Prefer wheels‑only pip installs: `pip install --only-binary :all: <pkgs>`.
  - Conda images: ensure PATH includes `/opt/conda/bin` so `/usr/bin/env python` resolves (compose sets this for `ingest`).
  - OpenCV: use `opencv-python-headless` to avoid GL/GUI deps; add `libgl1` only if needed.

- Quick checks:
  - `docker info` should list your DNS.
  - Disable BuildKit temporarily to isolate: `DOCKER_BUILDKIT=0 docker build .`
  - Smoke test base image DNS: `docker run --rm --dns 1.1.1.1 nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04 bash -lc 'apt-get update -qq && getent hosts deb.debian.org || true'`

See AGENTS.md for detailed guidance and rationale.

Helper CLI
- `volumes/bin/notesdb-rebuild.sh` — rebuilds the notes DB from schema and validates passages.
  - Usage: `volumes/bin/notesdb-rebuild.sh [--fill] [--dry-run] [--notes-db PATH] [--schema PATH] [--std-db PATH]`
  - Examples:
    - Rebuild + validate: `volumes/bin/notesdb-rebuild.sh`
    - Rebuild + validate + fill citations: `volumes/bin/notesdb-rebuild.sh --fill`
    - Preview citation fills only: `volumes/bin/notesdb-rebuild.sh --fill --dry-run`
