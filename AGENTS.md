# Repository Guidelines

## Project Goals & Scope
- Provide a self-hosted web UI to review handwritten scripture notes and general journals, with fast search, tagging, and filtering.
- Consolidate notes from scans (paper → PDFs/images) and existing text files into a single, queryable notes store.
- Correlate notes to the scriptures (Standard Works) with robust cross-references (book/chapter/verse), backlinks, and citations.
- Enable OCR for scanned documents, emitting per-page JSON and plain text with confidence and bounding boxes for future footnotes/citations.
- Support full‑text search across notes and scriptures, plus tags, collections, and simple metadata (dates, sources, notebooks).
- Keep data local-first and private by default; avoid external services. All runtime is containerized via Docker Compose.

## Containerization
- The stack runs in containers (API + web) via `docker compose`; use the GPU override file to enable CUDA when available.
- Persist data and models under `./volumes` on the host, mounted to `/data` in containers (`/data/scripdb`, `/data/ocr`, `/data/scans`, `/data/models`).
- Configure via `.env` (see `.env.example`) with key vars: `SQLITE_PATH`, `STANDARD_WORKS_DB`, `MODELS_DIR`. Do not commit secrets.

## Project Structure & Module Organization
- Root: `docker-compose.yml`, optional `docker-compose.gpu.yml`, `AGENTS.md`, `README.md`.
- Backend (Python): `backend/` with package code in `backend/personal_codex/` and tests in `backend/tests/` (mirrors package path).
- Frontend (React): `web/` with `src/`, `public/`, and `package.json`.
- Infra & scripts: `infra/` (DB, migrations, model assets) and `scripts/` (utility CLIs).

## Build, Test, and Development Commands
- Start stack (CPU): `docker compose up --build` (starts API and web). The API mounts `./volumes` to `/data` (put SQLite DB, scripts, and model weights here).
- Start with GPU: `docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build`.
- Rebuild a service: `docker compose build api` or `docker compose up -d --build web`.
- Backend tests: `docker compose run --rm api pytest -q` (add `-k pattern` to filter).
- Frontend tests: `docker compose run --rm web npm test -- --watch=false`.
- Lint/format backend: `docker compose run --rm api ruff check . && black --check .`.
- Lint/format frontend: `docker compose run --rm web npm run lint && npm run format:check`.

### Scriptures: DB Pipeline
- Make targets (host Python): `make pipeline` runs import → normalize → summary → check.
- Entry scripts: `scripts/init_standardworks_db.py`, `scripts/seed_standardworks.py`, `scripts/import_scriptures.py` (HTML → chapters/verses), `scripts/normalize_verses.py`, `scripts/normalize_metadata.py`, `scripts/summary_standardworks.py`, `scripts/check_normalization.py`.
- Data roots: HTML under `src/scripturedb/scriptures/`; DB at `volumes/scripdb/standardworks.db` (also via `STANDARD_WORKS_DB`).

### Initialize Standard Works DB
- Host Python: `python scripts/init_standardworks_db.py` creates `volumes/scripdb/standardworks.db` from `src/scripturedb/schema.sql`.
- SQLite CLI (if installed): `sqlite3 volumes/scripdb/standardworks.db < src/scripturedb/schema.sql`.

## CUDA/Torch Notes
- Use NVIDIA CUDA base images in `backend/Dockerfile` (e.g., `nvidia/cuda:12-runtime-ubuntu22.04`) and install `torch` matching CUDA.
- Local GPU: install NVIDIA drivers + NVIDIA Container Toolkit; run with the GPU override file above to enable `gpus: all`.

## Coding Style & Naming Conventions
- Python: Black (88 cols), Ruff; type hints for public APIs; 4‑space indent; names `snake_case` (funcs), `PascalCase` (classes), `UPPER_SNAKE` (consts).
- React/TS: 2‑space indent; components `PascalCase` in `web/src/components/`; hooks `useThing`; files `kebab-case.ts(x)` except components.

## Testing Guidelines
- Python: `pytest` + `pytest-cov`; target ≥80% coverage. Place tests under `backend/tests/` as `test_*.py`.
- React: Jest/Vitest + Testing Library; name files `*.test.tsx` colocated with components or under `__tests__/`.

## Commit & Pull Request Guidelines
- Conventional Commits (e.g., `feat(api): add verse index`, `fix(web): handle empty query`).
- PRs include: clear description (what/why), linked issues, screenshots for UI, and notes for DB/model or compose changes. Keep scope small; ensure CI green.

## Security & Configuration Tips
- Never commit secrets. Use `.env` files referenced by Compose; provide `.env.example`.
- Key env vars (api): `SQLITE_PATH=/data/personalcodex.db`, `STANDARD_WORKS_DB=/data/scripdb/standardworks.db`, `MODELS_DIR=/data/models`.
- Pin base images and package versions; avoid downloading model weights at build time—store them under `./volumes/models` and access via `/data/models`.

## Next Task: Scanned Files (OCR) – Guidance
- Input/outputs: place scans under `volumes/scans/` (host) → `/data/scans/` (api). Write OCR artifacts to `volumes/ocr/` → `/data/ocr/` and persist extracted text to notes DB at `SQLITE_PATH`.
- GPU usage: prefer CUDA models (Torch + OCR) when available; run on host or via Compose GPU override. Respect `MODELS_DIR=/data/models` for weights.
- Suggested layout: add scripts under `scripts/` (e.g., `scripts/ocr_import.py`) or a `backend/personal_codex/ocr/` module if integrating with the API.
- Conventions: process PDFs and images; chunk pages; emit per-page JSON and plain text; capture confidence and bounding boxes for future footnotes/citations.
- Testing: provide a small sample in `volumes/scans/sample/` and a dry-run mode that reads one file and prints a summary.

## Agent-Specific Instructions
- Prefer dockerized workflows; avoid host-specific steps. If adding services, update `compose.yml` and document ports/env.
- Keep patches minimal and aligned to the structure above; discuss major tooling changes in an issue first.

### Modularity & Scripts
- Prefer a practical, modular design: small, focused scripts and components that compose well. Avoid monoliths when a simple seam helps maintainability.
- All runtime/ingestion scripts should live under `volumes/bin/` in the repo and are mounted into containers at `/data/bin/`.
- Ensure `/data/bin` is on the PATH for containers that need these tools (compose already sets this for `api` and `ingest`).
- Keep orchestrators thin (dispatch, logging, idempotency) and delegate heavy lifting to dedicated subcommands.
