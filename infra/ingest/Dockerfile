# syntax=docker/dockerfile:1.7
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN --network=host <<'SH'
set -eux
echo 'Acquire::Retries "3"; Acquire::ForceIPv4 "true";' >/etc/apt/apt.conf.d/80-build
apt-get update
apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-eng libtesseract-dev libglib2.0-0 \
 && rm -rf /var/lib/apt/lists/*
SH

RUN pip install --no-cache-dir PyMuPDF>=1.23.7 Pillow

ENV PATH=/data/bin:$PATH

WORKDIR /

CMD ["newdata-ingest"]
