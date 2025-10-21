# syntax=docker/dockerfile:1.7
FROM docker.io/pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/data/bin:$PATH \
    HF_HOME=/data/models

RUN --network=host <<'SH'
set -eux
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir \
  "sentence-transformers>=3.0,<4" \
  croniter
python - <<'PY'
import torch
print("Torch:", torch.__version__)
PY
SH

WORKDIR /

CMD ["notesdb-embeddings"]

