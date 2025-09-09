# syntax=docker/dockerfile:1.7
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

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
  "opencv-python-headless>=4.8" \
  Pillow torchvision
# Ensure non-headless OpenCV is not present (eliminate libGL runtime need)
python - <<'PY'
import sys, subprocess
# Try to remove opencv-python if it got pulled as a dependency
subprocess.run([sys.executable, '-m', 'pip', 'uninstall', '-y', 'opencv-python'], check=False)
PY
# Sanity: verify cv2 import is available in runtime
python - <<'PY'
import sys
print('Python:', sys.executable)
import cv2
print('cv2 version:', cv2.__version__)
PY
SH

WORKDIR /

CMD ["newdata-ingest"]
