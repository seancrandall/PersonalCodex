# syntax=docker/dockerfile:1.7
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/data/bin:$PATH

# System libs for OCR and OpenCV, with host networking for DNS
RUN --network=host <<'SH'
set -eux
echo 'Acquire::Retries "3"; Acquire::ForceIPv4 "true";' >/etc/apt/apt.conf.d/80-build
apt-get update
apt-get install -y --no-install-recommends \
  tesseract-ocr tesseract-ocr-eng \
  libglib2.0-0 libgl1 \
 && rm -rf /var/lib/apt/lists/*
SH

# Install Python deps (use host networking for reliable DNS); prefer headless OpenCV
RUN --network=host <<'SH'
set -eux
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir \
  "pymupdf==1.24.11" \
  "python-doctr[torch]==0.9.0" \
  "opencv-python-headless>=4.8" \
  Pillow torchvision
# Ensure non-headless OpenCV is not present (eliminate libGL runtime need)
python - <<'PY'
import sys, subprocess
try:
    import cv2  # noqa: F401
    import pkgutil
    # If this is the headless build, module path ends with "cv2/python-3.x" and has no Qt backends
    # Attempt to uninstall non-headless if both installed
    subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', 'opencv-python'], check=False)
except Exception:
    pass
PY
SH

WORKDIR /

CMD ["newdata-ingest"]
