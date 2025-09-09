# syntax=docker/dockerfile:1.7
FROM pytorch/pytorch:2.3.1-cuda12.1-cudnn8-runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/data/bin:$PATH

# Install Python deps (use host networking for reliable DNS); prefer headless OpenCV
RUN --network=host <<'SH'
set -eux
python -m pip install --upgrade pip setuptools wheel
# Try upgrading torch to a version that allows loading .bin weights securely
python - <<'PY'
import subprocess, sys
def try_install(url, torch_ver, tv_ver, ta_ver):
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-cache-dir',
                        '--index-url', url,
                        f'torch=={torch_ver}', f'torchvision=={tv_ver}', f'torchaudio=={ta_ver}'], check=True)
        print('Upgraded torch to', torch_ver)
        return True
    except Exception as e:
        print('Torch upgrade attempt failed:', e)
        return False

candidates = [
    ('https://download.pytorch.org/whl/cu121', '2.6.0', '0.21.0', '2.6.0'),
    ('https://download.pytorch.org/whl/cu121', '2.5.1', '0.20.1', '2.5.1'),
]
ok=False
for url, tv, vv, av in candidates:
    if try_install(url, tv, vv, av):
        ok=True
        break
if not ok:
    print('Proceeding with existing torch; .bin weights may be blocked by security gate')
PY
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
import cv2
print('cv2 version:', cv2.__version__)
PY
SH

WORKDIR /

CMD ["newdata-ingest"]
