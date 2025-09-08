#!/bin/sh
set -eu

export PATH="/data/bin:${PATH}"

echo "[sanity] PATH=$PATH"
echo "[sanity] Starting ingestion sanity run (dry-run stubs)"

echo "[sanity] 1) newdata-ingest --dry-run"
newdata-ingest --dry-run || true

set -- /data/newdata/*
if [ -e "$1" ]; then
  echo "[sanity] 2) classify-doc on /data/newdata/*"
  classify-doc /data/newdata/* || true
else
  echo "[sanity] 2) classify-doc: no files under /data/newdata, skipping"
fi

echo "[sanity] 3) pdf-to-pages --dry-run (placeholder path)"
pdf-to-pages /data/newdata/sample.pdf --dry-run || true

echo "[sanity] 4) ocr-image --dry-run on directory"
ocr-image /data/newdata --dry-run || true

echo "[sanity] 5) text-to-md --dry-run (placeholder path)"
text-to-md /data/newdata/sample.txt --dry-run || true

echo "[sanity] 6) index-notes --dry-run"
index-notes --dry-run || true

echo "[sanity] Done."
