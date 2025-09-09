# GPU-enabled Kraken runner (Python 3.11 + CUDA 12.1)
# Uses NVIDIA CUDA runtime and installs PyTorch CUDA wheels + Kraken.

FROM nvidia/cuda:12.1.1-cudnn8-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PIP_NO_CACHE_DIR=1

# Install Python 3.x and basics (Ubuntu 22.04 ships Python 3.10)
RUN apt-get update -qq && apt-get install -y --no-install-recommends \
    python3 python3-venv python3-pip ca-certificates git curl \
    libglib2.0-0 libsm6 libxext6 libxrender1 \
  && ln -sf /usr/bin/python3 /usr/bin/python \
  && python -m pip install --upgrade pip setuptools wheel \
  && rm -rf /var/lib/apt/lists/*

# Install CUDA-enabled PyTorch matching CUDA 12.1 and Kraken
RUN python -m pip install --index-url https://download.pytorch.org/whl/cu121 \
      torch torchvision torchaudio \
    && python -m pip install "kraken==5.3.0" opencv-python-headless

# Prepare work directories and PATH to include /data/bin
WORKDIR /work
ENV PATH="/data/bin:${PATH}" \
    MODELS_DIR=/data/models \
    DOCTR_BACKEND=pytorch \
    DOCTR_CACHE_DIR=/data/models/doctr \
    MPLCONFIGDIR=/tmp/mpl

# Default command shows kraken help; override with `kraken-ocr` in compose/run
CMD ["kraken", "--help"]
