#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$ROOT_DIR/.tools"
NODE_VERSION="${NODE_VERSION:-22.14.0}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-5173}"
OPEN_BROWSER="${OPEN_BROWSER:-1}"
BACKEND_PID=""
FRONTEND_PID=""

cd "$ROOT_DIR"
mkdir -p "$TOOLS_DIR"

info() { printf '\033[1;34m[Chord Deck]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[Chord Deck]\033[0m %s\n' "$*" >&2; exit 1; }

download() {
  command -v curl >/dev/null 2>&1 || die "需要 curl 才能自动下载工具，请安装 curl 后重试。"
  curl -fL --retry 3 --retry-delay 1 "$1" -o "$2"
}

setup_uv() {
  if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
    return
  fi
  UV_BIN="$TOOLS_DIR/uv"
  if [[ ! -x "$UV_BIN" ]]; then
    info "未检测到 uv，正在下载项目本地副本…"
    local installer
    installer="$(mktemp "${TMPDIR:-/tmp}/chord-deck-uv.XXXXXX")"
    download "https://astral.sh/uv/install.sh" "$installer"
    UV_UNMANAGED_INSTALL="$TOOLS_DIR" sh "$installer"
    rm -f "$installer"
  fi
  [[ -x "$UV_BIN" ]] || die "uv 自动安装失败。"
}

setup_node() {
  if command -v node >/dev/null 2>&1 && command -v npm >/dev/null 2>&1; then
    NODE_BIN_DIR=""
    return
  fi

  local os arch archive node_dir url
  case "$(uname -s)" in
    Darwin) os="darwin" ;;
    Linux) os="linux" ;;
    *) die "当前启动脚本支持 macOS 和 Linux；Windows 请使用 PowerShell 启动脚本。" ;;
  esac
  case "$(uname -m)" in
    arm64|aarch64) arch="arm64" ;;
    x86_64|amd64) arch="x64" ;;
    *) die "不支持的 CPU 架构：$(uname -m)" ;;
  esac

  node_dir="$TOOLS_DIR/node-v${NODE_VERSION}-${os}-${arch}"
  if [[ ! -x "$node_dir/bin/node" || ! -x "$node_dir/bin/npm" ]]; then
    archive="$TOOLS_DIR/node-v${NODE_VERSION}-${os}-${arch}.tar.gz"
    url="https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-${os}-${arch}.tar.gz"
    info "未检测到 Node.js/npm，正在下载项目本地 Node.js v${NODE_VERSION}…"
    download "$url" "$archive"
    tar -xzf "$archive" -C "$TOOLS_DIR"
    rm -f "$archive"
  fi
  [[ -x "$node_dir/bin/node" && -x "$node_dir/bin/npm" ]] || die "Node.js 自动安装失败。"
  NODE_BIN_DIR="$node_dir/bin"
  export PATH="$NODE_BIN_DIR:$PATH"
}

ensure_environments() {
  info "同步主 Python 环境…"
  "$UV_BIN" sync --locked --managed-python

  if [[ ! -d "$ROOT_DIR/frontend/node_modules" ]]; then
    info "安装前端依赖…"
    (cd "$ROOT_DIR/frontend" && npm ci --no-audit --no-fund)
  fi

  local lv_python="$ROOT_DIR/.venv-lv/bin/python"
  if [[ ! -x "$lv_python" ]] || ! "$lv_python" -c 'import torch, lv_chordia' >/dev/null 2>&1; then
    info "安装 LV-Chordia 独立环境（首次可能需要较长时间和较多磁盘空间）…"
    "$UV_BIN" venv "$ROOT_DIR/.venv-lv" --python "$PYTHON_VERSION"
    "$UV_BIN" pip install --python "$lv_python" lv-chordia
  fi
}

wait_for_url() {
  local url="$1"
  "$PYTHON_BIN" - "$url" <<'PY'
import sys
import time
import urllib.request

url = sys.argv[1]
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=1):
            raise SystemExit(0)
    except Exception:
        time.sleep(0.5)
raise SystemExit(f"服务未能在规定时间内启动：{url}")
PY
}

open_browser() {
  local url="http://127.0.0.1:${FRONTEND_PORT}/"
  case "$(uname -s)" in
    Darwin) open "$url" >/dev/null 2>&1 & ;;
    Linux) (xdg-open "$url" >/dev/null 2>&1 || true) & ;;
  esac
}

cleanup() {
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

setup_uv
setup_node
ensure_environments

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"
[[ -x "$PYTHON_BIN" ]] || die "主 Python 环境创建失败：$PYTHON_BIN"
info "检查运行环境…"
"$PYTHON_BIN" "$ROOT_DIR/scripts/check_env.py"

info "启动后端和前端…"
"$PYTHON_BIN" -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" &
BACKEND_PID=$!
(cd "$ROOT_DIR/frontend" && npm run dev -- --host 127.0.0.1 --port "$FRONTEND_PORT") &
FRONTEND_PID=$!

wait_for_url "http://127.0.0.1:${FRONTEND_PORT}/"
info "Frontend: http://127.0.0.1:${FRONTEND_PORT}/"
info "Backend: http://127.0.0.1:${BACKEND_PORT}/"
if [[ "$OPEN_BROWSER" == "1" ]]; then
  open_browser
fi
wait "$BACKEND_PID" "$FRONTEND_PID"
