# syntax=docker/dockerfile:1.7
FROM pytorch/pytorch:2.6.0-cuda12.1-cudnn9-runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/data/bin:$PATH

# Install Python deps (use host networking for reliable DNS); prefer headless OpenCV
RUN --network=host <<'SH'
set -eux
python -m pip install --upgrade pip setuptools wheel
pip install --no-cache-dir \
  "pymupdf==1.24.11" \
  "python-doctr[torch]==0.9.0" \
  "transformers>=4.41,<5" \
  sentencepiece \
  "opencv-python-headless>=4.8" \
  Pillow torchvision
# Ensure non-headless OpenCV is not present (eliminate libGL runtime need)
python - <<'PY'
import sys, subprocess
# Try to remove opencv-python if it got pulled as a dependency
subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', 'opencv-python'], check=False)
PY
# Ensure headless OpenCV files are present after uninstall step
python -m pip install --no-cache-dir --upgrade --force-reinstall opencv-python-headless==4.11.0.86
# Sanity: verify cv2 import is available in runtime
python - <<'PY'
import sys
print('Python:', sys.executable)
import torch, torchvision
print('Torch:', torch.__version__)
print('Torchvision:', torchvision.__version__)
import cv2
print('cv2 version:', cv2.__version__)
PY
SH

WORKDIR /

CMD ["newdata-ingest"]
