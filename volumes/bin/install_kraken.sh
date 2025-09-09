#!/usr/bin/env bash
set -euo pipefail

# Install kraken into a local venv under volumes/bin and smoke-test the CLI.

cd "$(dirname "$0")"

VENV_DIR=${VENV_DIR:-.venv-kraken}
PY=${PYTHON:-python3}

if [[ ! -d "$VENV_DIR" ]]; then
  echo "[+] Creating venv at $(pwd)/$VENV_DIR (with system site packages)"
  "$PY" -m venv --system-site-packages "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

python -m pip install --upgrade pip wheel setuptools
echo "[+] Installing kraken"
python -m pip install --upgrade "kraken>=4.3.0"

echo "[+] kraken version:" && kraken --version || true

echo "[i] To download a model (example):"
echo "    source $VENV_DIR/bin/activate"
echo "    mkdir -p ../../volumes/models/kraken && cd ../../volumes/models/kraken"
echo "    kraken get en_best  # or another model id"
echo "[i] Then run: volumes/bin/kraken-ocr --input src/tmp/trocr --pattern '*.png' --device cuda --model-path volumes/models/kraken/en_best.mlmodel"

