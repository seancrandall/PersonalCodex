# syntax=docker/dockerfile:1.7
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    TZ=UTC \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# OS deps (host networking so DNS resolution uses the host)
RUN --network=host \
    --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    <<'SH'
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
SH

# Make `python` symlink, drop PEP 668 guard, and upgrade pip/setuptools/wheel
# (also with host networking to avoid any index resolution hiccups)
RUN --network=host set -eux; \
    if ! command -v python >/dev/null; then ln -s /usr/bin/python3 /usr/local/bin/python; fi; \
    rm -f /usr/lib/python3.*/EXTERNALLY-MANAGED; \
    python3 -m pip install --upgrade pip setuptools wheel

# Optional non-root user (handy if you bind-mount host dirs)
ARG USERNAME=trainer
ARG UID=1000
ARG GID=1000
RUN set -eux; \
    groupadd -g "${GID}" "${USERNAME}" || true; \
    useradd -m -u "${UID}" -g "${GID}" -s /bin/bash "${USERNAME}" || true

WORKDIR /workspace

COPY requirements.txt /workspace/requirements.txt

# Torch 2.6 + CUDA 12.4
RUN pip install --upgrade pip \
 && pip install --no-cache-dir \
      torch==2.6.0+cu124 torchvision==0.21.0+cu124 torchaudio==2.6.0+cu124 \
      --index-url https://download.pytorch.org/whl/cu124 \
 && pip install --no-cache-dir \
      "bitsandbytes>=0.45.2" "triton>=3.0.0" \
 && pip install --no-cache-dir -r /workspace/requirements.txt

# ---- Build-time verification that torchrun exists ----
# Will fail the build if torch/torchrun is missing
RUN python - <<'PY'
import sys
import torch
import importlib
# this import throws if torchrun is not installed
import torch.distributed.run as _verify
print("OK torch", torch.__version__)
PY

# Help bitsandbytes find CUDA
ENV LD_LIBRARY_PATH=/usr/local/cuda/lib64:${LD_LIBRARY_PATH}

# Create common mount points (match your compose volumes)
RUN mkdir -p /workspace/training_set /workspace/adapters

# If you later add requirements.txt, keep the network hint on that step too:
# COPY requirements.txt /tmp/requirements.txt
# RUN --network=host python -m pip install -r /tmp/requirements.txt

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["bash"]
