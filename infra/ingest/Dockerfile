# syntax=docker/dockerfile:1.7
FROM jbarlow83/ocrmypdf:latest

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/data/bin:$PATH

# Ensure pip is available, then install PyMuPDF from wheels
RUN set -eux; \
    python3 -m ensurepip --upgrade || true; \
    python3 -m pip install --no-cache-dir --upgrade pip setuptools wheel || true; \
    python3 -m pip install --no-cache-dir "pymupdf==1.24.11" Pillow

WORKDIR /

CMD ["newdata-ingest"]
