# Repository Guidelines

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

## Agent-Specific Instructions
- Prefer dockerized workflows; avoid host-specific steps. If adding services, update `compose.yml` and document ports/env.
- Keep patches minimal and aligned to the structure above; discuss major tooling changes in an issue first.
