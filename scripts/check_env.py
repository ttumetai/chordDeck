#!/usr/bin/env python3
"""检查本地运行 Chord Deck 所需的 Python、音频和前端环境。"""
import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
errors = 0


def ok(message):
    print(f"[ok]   {message}")


def warn(message):
    print(f"[warn] {message}")


def fail(message):
    global errors
    errors += 1
    print(f"[fail] {message}")


if sys.version_info >= (3, 9):
    ok(f"Python {sys.version.split()[0]}")
else:
    fail("Python >= 3.9 required")

for module in ("fastapi", "uvicorn", "numpy", "scipy", "librosa", "soundfile", "chord_extractor", "madmom_infer"):
    if importlib.util.find_spec(module):
        ok(f"Python module: {module}")
    else:
        fail(f"Python module missing: {module} (run uv sync)")

vamp_roots = [Path(p).expanduser() for p in os.getenv("VAMP_PATH", "~/vamp-plugins").split(os.pathsep) if p]
vamp_files = [p for root in vamp_roots if root.is_dir() for p in root.rglob("nnls-chroma.*")]
if vamp_files:
    ok(f"VAMP NNLS-Chroma: {vamp_files[0]}")
else:
    warn("VAMP NNLS-Chroma not found; Chordino will fall back to librosa")

model_cache = ROOT / "backend" / ".model_cache"
if model_cache.is_dir() and any(model_cache.rglob("*")):
    ok(f"DeepChroma model cache: {model_cache}")
else:
    warn("DeepChroma model cache is empty; first DeepChroma run may download weights")

npm = shutil.which("npm")
if npm:
    ok(f"npm: {shutil.which('npm')}")
else:
    fail("npm not found")

frontend = ROOT / "frontend"
if (frontend / "package.json").is_file() and (frontend / "node_modules").is_dir():
    ok("frontend dependencies installed")
else:
    fail("frontend dependencies missing (cd frontend && npm install)")

if npm and (frontend / "node_modules").is_dir():
    result = subprocess.run(
        [npm, "run", "build"], cwd=frontend, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
    )
    if result.returncode == 0:
        ok("frontend production build")
    else:
        fail(f"frontend build failed: {result.stderr.strip().splitlines()[-1] if result.stderr.strip() else 'unknown error'}")

if errors:
    print(f"\nEnvironment check failed with {errors} issue(s).")
    raise SystemExit(1)
print("\nEnvironment check passed. Warnings above are optional fallbacks.")
