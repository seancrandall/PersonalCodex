#!/usr/bin/env python3
"""
Thin orchestrator to run OCR on handwriting samples.

Behavior:
- Default target: repo_root/src/tmp/trocr/*.png
- Prefers running src/tmp/trocr/run_trocr.py (uses local model dir) under its venv if present.
- Falls back to repo_root/scripts/ocr.py if trocr runner/venv not available.

Environment:
- Respects MODELS_DIR if set; else uses repo_root/volumes/models for local weights.

Usage:
- volumes/bin/ocr.py                   # process default glob in trocr folder
- volumes/bin/ocr.py --dry-run         # list images and chosen runner
- volumes/bin/ocr.py --overwrite       # overwrite existing .txt
- volumes/bin/ocr.py --pattern '*.png' # custom glob within trocr folder
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    # volumes/bin/ocr.py -> root is parents[2]
    return Path(__file__).resolve().parents[2]


def find_python_for_trocr(trocr_dir: Path) -> Path | None:
    # Prefer venv python under src/tmp/trocr/.venv
    venv_py = trocr_dir / ".venv" / "bin" / "python"
    if venv_py.exists():
        return venv_py
    # Fallback to system python
    py = shutil.which("python3") or shutil.which("python")
    return Path(py) if py else None


def main() -> int:
    root = repo_root()
    trocr_dir = root / "src" / "tmp" / "trocr"
    default_models = root / "volumes" / "models"

    ap = argparse.ArgumentParser(description="Run OCR on trocr/*.png using TrOCR")
    ap.add_argument("--pattern", default="*.png", help="Glob of images within trocr dir")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    ap.add_argument("--dry-run", action="store_true", help="Print plan and exit")
    args = ap.parse_args()

    if not trocr_dir.exists():
        print(f"trocr directory not found: {trocr_dir}", file=sys.stderr)
        return 2

    # Ensure MODELS_DIR points to local volumes/models if not provided
    env = os.environ.copy()
    env.setdefault("MODELS_DIR", str(default_models))

    # Prefer dedicated trocr runner if present
    trocr_runner = trocr_dir / "run_trocr.py"
    scripts_runner = root / "scripts" / "ocr.py"

    use_trocr = trocr_runner.exists()
    runner_desc = "trocr/run_trocr.py" if use_trocr else "scripts/ocr.py"

    # Build command
    if use_trocr:
        py = find_python_for_trocr(trocr_dir)
        if not py:
            print("python not found to run trocr", file=sys.stderr)
            return 3
        cmd = [str(py), str(trocr_runner), "--pattern", args.pattern]
        if args.overwrite:
            cmd.append("--overwrite")
        cwd = trocr_dir
    else:
        # Fallback uses the general OCR script; pass the trocr dir as input
        py = shutil.which("python3") or shutil.which("python")
        if not py or not scripts_runner.exists():
            print("Fallback runner not available (scripts/ocr.py)", file=sys.stderr)
            return 4
        cmd = [str(py), str(scripts_runner), str(trocr_dir)]
        # scripts/ocr.py writes .txt by default; no overwrite flag there
        cwd = root

    # Discover a few images for preview
    matches = sorted([p for p in trocr_dir.glob(args.pattern) if p.is_file()])
    if args.dry_run:
        print(f"Runner: {runner_desc}")
        print(f"CWD: {cwd}")
        print(f"MODELS_DIR: {env.get('MODELS_DIR')}")
        print(f"Command: {' '.join(cmd)}")
        print(f"Found {len(matches)} matching files:")
        for p in matches[:10]:
            print(f" - {p.name}")
        if len(matches) > 10:
            print(" ...")
        return 0

    if not matches:
        print(f"No files match pattern {args.pattern!r} in {trocr_dir}")
        return 0

    print(f"[+] Running {runner_desc} on {len(matches)} file(s) in {trocr_dir}")
    try:
        res = subprocess.run(cmd, cwd=str(cwd), env=env, check=False)
        return res.returncode
    except FileNotFoundError as e:
        print(f"Failed to execute runner: {e}", file=sys.stderr)
        return 5


if __name__ == "__main__":
    raise SystemExit(main())

