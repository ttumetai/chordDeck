"""Detect optional chord engines without loading their models."""

import importlib.util
import os
import platform
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module_available(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def _vamp_status() -> tuple[bool, str]:
    roots = [
        Path(path).expanduser()
        for path in os.getenv("VAMP_PATH", "~/vamp-plugins").split(os.pathsep)
        if path
    ]
    candidates = [
        path
        for root in roots
        if root.is_dir()
        for path in root.rglob("nnls-chroma.*")
        if path.is_file()
    ]
    if not candidates:
        return False, "未找到 NNLS-Chroma VAMP 插件"

    inspector = shutil.which("file")
    if not inspector:
        return True, "已找到 NNLS-Chroma 插件"
    current = platform.machine().lower()
    for candidate in candidates:
        result = subprocess.run(
            [inspector, str(candidate)], capture_output=True, text=True, check=False
        )
        description = result.stdout.lower()
        if current in {"arm64", "aarch64"} and ("arm64" in description or "aarch64" in description):
            return True, "已找到匹配当前架构的 NNLS-Chroma 插件"
        if current in {"x86_64", "amd64"} and ("x86_64" in description or "x86-64" in description):
            return True, "已找到匹配当前架构的 NNLS-Chroma 插件"
    return False, f"VAMP 插件架构与当前系统（{platform.machine()}）不匹配"


def _lv_status() -> tuple[bool, str]:
    python = Path(
        os.getenv("CHORD_LV_PYTHON", str(ROOT / ".venv-lv" / "bin" / "python"))
    ).expanduser()
    if not python.is_file():
        return False, "未安装独立 .venv-lv 环境"
    try:
        probe = subprocess.run(
            [
                str(python),
                "-c",
                "import platform, torch, lv_chordia; print(platform.machine(), torch.backends.mps.is_available())",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "检测 lv-chordia 超时"
    if probe.returncode:
        return False, "lv-chordia 或 PyTorch 无法导入"
    parts = probe.stdout.strip().split()
    mps = len(parts) > 1 and parts[-1].lower() == "true"
    return True, "支持 MPS，可使用 CPU" if mps else "支持 CPU；当前无可用 MPS"


def detect_engines() -> dict:
    librosa_ok = _module_available("librosa") and _module_available("soundfile")
    deepchroma_ok = _module_available("madmom_infer")
    chordino_ok, chordino_reason = _vamp_status()
    lv_ok, lv_reason = _lv_status()
    engines = {
        "auto": {"available": librosa_ok, "reason": "默认回退链路可用" if librosa_ok else "librosa 或 soundfile 未安装"},
        "deepchroma": {"available": deepchroma_ok, "reason": "依赖已安装" if deepchroma_ok else "madmom-infer 未安装"},
        "chordino": {"available": chordino_ok, "reason": chordino_reason},
        "lv-chordia": {"available": lv_ok, "reason": lv_reason},
    }
    return {
        "machine": platform.machine(),
        "engines": engines,
        "recommended": "lv-chordia" if lv_ok else "auto",
    }
