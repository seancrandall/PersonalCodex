#!/usr/bin/env bash
set -euo pipefail

# Rebuild notes DB from schema and validate/optionally fill citations.
# Defaults assume running from repo root with standard paths.

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
cd "${REPO_ROOT}"

NOTES_DB=${NOTES_DB:-volumes/notesdb/notes.db}
SCHEMA=${SCHEMA:-src/notesdb/schema.sql}
STD_DB=${STD_DB:-volumes/scripdb/standardworks.db}

FILL=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage: volumes/bin/notesdb-rebuild.sh [--fill] [--dry-run] [--notes-db PATH] [--schema PATH] [--std-db PATH]

Options:
  --fill          Fill missing passage.citation labels after validation
  --dry-run       With --fill, preview citation updates without writing
  --notes-db PATH Override notes DB path (default: ${NOTES_DB})
  --schema PATH   Override schema path (default: ${SCHEMA})
  --std-db PATH   Override standard works DB path (default: ${STD_DB})
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --fill) FILL=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --notes-db) NOTES_DB=$2; shift 2 ;;
    --schema) SCHEMA=$2; shift 2 ;;
    --std-db) STD_DB=$2; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

echo "[notesdb] Building ${NOTES_DB} from ${SCHEMA}"
mkdir -p "$(dirname "${NOTES_DB}")"
sqlite3 "${NOTES_DB}" < "${SCHEMA}"

echo "[notesdb] Validating passages against ${STD_DB}"
if ${FILL}; then
  if ${DRY_RUN}; then
    python scripts/validate_notes_passages.py --notes-db "${NOTES_DB}" --std-db "${STD_DB}" --fill-citations --dry-run
  else
    python scripts/validate_notes_passages.py --notes-db "${NOTES_DB}" --std-db "${STD_DB}" --fill-citations
  fi
else
  python scripts/validate_notes_passages.py --notes-db "${NOTES_DB}" --std-db "${STD_DB}"
fi

echo "[notesdb] Done."

