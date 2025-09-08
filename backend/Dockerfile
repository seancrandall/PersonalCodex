# syntax=docker/dockerfile:1.7
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# OS deps (host networking so DNS resolution uses the host) with apt caching
RUN --network=host \
    --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt <<'SH'
set -eux

# Temporarily disable NVIDIA list files if present (prevents conflicts)
tmp=/tmp/apt-disabled; mkdir -p "$tmp"
for f in /etc/apt/sources.list.d/*cuda*.list /etc/apt/sources.list.d/*nvidia*.list; do
  [ -e "$f" ] && mv "$f" "$tmp"/
done

# Apt behavior tweaks
echo 'Acquire::Retries "3"; Acquire::ForceIPv4 "true";' >/etc/apt/apt.conf.d/80-build

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl wget git git-lfs vim nano build-essential pkg-config \
  software-properties-common unzip python3 python3-pip python3-venv python3-dev tini
update-ca-certificates

# Restore lists and clean
mv "$tmp"/*.list /etc/apt/sources.list.d/ 2>/dev/null || true
rm -rf /var/lib/apt/lists/*
ln -sf /usr/bin/python3 /usr/local/bin/python
SH

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip setuptools wheel \
 && python -m pip install -r /app/requirements.txt

ENV SQLITE_PATH=/data/personalcodex.db \
    STANDARD_WORKS_DB=/data/scripdb/standardworks.db \
    MODELS_DIR=/data/models

CMD ["bash", "-lc", "uvicorn app.main:app --host 0.0.0.0 --port 8000"]
