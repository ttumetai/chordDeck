"""和弦识别 Web 应用 — FastAPI 后端。

功能:
    * 上传音频 → 计算 MD5 → 命中缓存则直接返回历史结果
    * 新音频存入 backend/resources/（用户删除原文件不影响回放）
    * 分析结果以 SQLite (backend/analyses.db) 持久化，提供历史记录

运行方式（在项目根目录）:
    uv run uvicorn backend.main:app --reload --port 8000

接口:
    POST   /api/analyze        上传音频并返回和弦序列（MD5 相同则命中缓存）
    GET    /api/analyses/{id}  按 ID 取回历史分析结果
    POST   /api/analyses/{id}/reanalyze  用已存音频重新识别并更新缓存
    DELETE /api/analyses/{id}  删除历史记录及其音频文件
    GET    /api/history        历史记录列表（按时间倒序）
    GET    /api/audio/{name}   取回资源目录中的音频文件
    GET    /api/health         健康检查
    其余路径托管 frontend/dist 构建产物（生产模式单服务部署）
"""
import hashlib
import json
import logging
import os
import sqlite3
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from . import db
    from .chords import (
        collapse_duplicates,
        extract_beats,
        extract_chords,
        get_duration,
        postprocess,
        simplify_chord,
    )
except ImportError:  # 以 `uvicorn main:app` 从 backend/ 目录启动时
    import db
    from chords import (
        collapse_duplicates,
        extract_beats,
        extract_chords,
        get_duration,
        postprocess,
        simplify_chord,
    )

BASE_DIR = Path(__file__).resolve().parent
RESOURCES_DIR = BASE_DIR / "resources"  # 音频文件的持久化副本
RESOURCES_DIR.mkdir(exist_ok=True)
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"

ALLOWED_EXTS = {
    ".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac",
    ".webm", ".opus", ".aiff", ".aif",
}
MAX_UPLOAD_BYTES = int(os.getenv("CHORD_MAX_UPLOAD_MB", "200")) * 1024 * 1024
ASYNC_DURATION_SECONDS = float(os.getenv("CHORD_ASYNC_DURATION_SECONDS", "30"))
_executor = ThreadPoolExecutor(
    max_workers=max(1, int(os.getenv("CHORD_ANALYZE_WORKERS", "2")))
)
_tasks = {}
_tasks_lock = threading.Lock()

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("chord-app")

db.init_db()


def _backfill_simple():
    """为旧记录补充 chords_simple，并统一 chords 为合并后的「完整」标记。"""
    for rec in db.list_all():
        full, simple = postprocess(db.chords_of(rec))
        db.update_full(rec["id"], full)
        db.update_simple(rec["id"], simple)
    logger.info("历史记录后处理已就绪（完整/简化两档）")


_backfill_simple()

app = FastAPI(title="Chord Recognition API", version="1.2.0")

# 开发期允许 Vite (5173) 跨域直连；生产由 Vite 代理或同源托管，不依赖此配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── 工具函数 ──────────────────────────────────────────────

def _save_and_hash(stream, dest: Path, max_bytes=None):
    """边写盘边计算 MD5，返回 (md5, file_size)。"""
    max_bytes = MAX_UPLOAD_BYTES if max_bytes is None else max_bytes
    h = hashlib.md5()
    size = 0
    with dest.open("wb") as f:
        while chunk := stream.read(1024 * 1024):
            if size + len(chunk) > max_bytes:
                raise ValueError(f"音频文件超过 {max_bytes // 1024 // 1024} MB 限制")
            h.update(chunk)
            f.write(chunk)
            size += len(chunk)
    return h.hexdigest(), size


def _task_update(task_id: str, **updates):
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task:
            task.update(updates)


def _task_response(task_id: str):
    with _tasks_lock:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="分析任务不存在")
        return dict(task)


def _analyze_record(record: dict, dest: Path):
    """执行识别、后处理和节拍提取；同步接口与后台任务共用。"""
    logger.info("开始识别: %s (engine=%s, md5=%s)", record["filename"], record["engine"], record["md5"])
    changes, source = extract_chords(str(dest), record["engine"])
    chords_full, chords_simple = postprocess(changes)
    bpm, beats, _bsrc = extract_beats(str(dest))
    if bpm is None:
        logger.info("节拍未检出: %s", record["filename"])
    else:
        logger.info("节拍识别: %s BPM=%s (%d 拍, %s)", record["filename"], bpm, len(beats), _bsrc)
    record.update(
        source=source,
        chords=chords_full,
        chords_simple=chords_simple,
        bpm=bpm,
        beats=beats,
    )
    return record


def _run_analyze_task(task_id: str, record: dict, dest: Path):
    _task_update(task_id, status="running", progress=0.05, stage="extracting")
    try:
        record = _analyze_record(record, dest)
        _task_update(task_id, progress=0.85, stage="saving")
        try:
            db.insert(record)
        except sqlite3.IntegrityError:
            existing = db.find_by_md5(record["md5"], record["engine"])
            if not existing:
                raise
            _task_update(task_id, progress=1, stage="done", status="done", cached=True,
                         result=_analysis_response(existing, cached=True))
            return
        _task_update(task_id, progress=1, stage="done", status="done", cached=False,
                     result=_analysis_response(db.find_by_id(record["id"]), cached=False))
    except Exception as exc:  # noqa: BLE001
        logger.exception("后台和弦识别失败: %s", exc)
        _task_update(task_id, status="error", progress=1, stage="error", error=str(exc))


def _run_reanalyze_task(task_id: str, rid: str, engine: str, record: dict, audio_path: Path):
    _task_update(task_id, status="running", progress=0.05, stage="extracting")
    try:
        changes, source = extract_chords(str(audio_path), engine)
        chords_full, chords_simple = postprocess(changes)
        _task_update(task_id, progress=0.75, stage="saving")
        duration = get_duration(str(audio_path))
        slot = db.find_by_md5(record["md5"], engine)
        if slot:
            target_id = slot["id"]
            db.update_analysis(target_id, chords=chords_full, chords_simple=chords_simple,
                               source=source, duration=duration)
        else:
            target_id = uuid.uuid4().hex[:12]
            db.insert({"id": target_id, "md5": record["md5"], "filename": record["filename"],
                       "stored_name": record["stored_name"], "file_size": record["file_size"],
                       "duration": duration, "source": source, "engine": engine,
                       "chords": chords_full, "chords_simple": chords_simple})
        db.clear_edited(target_id)
        _task_update(task_id, progress=1, stage="done", status="done", cached=False,
                     result=_analysis_response(db.find_by_id(target_id), cached=False))
    except Exception as exc:  # noqa: BLE001
        logger.exception("后台重新识别失败: %s", exc)
        _task_update(task_id, status="error", progress=1, stage="error", error=str(exc))


def _new_task():
    task_id = uuid.uuid4().hex[:12]
    with _tasks_lock:
        _tasks[task_id] = {
            "task_id": task_id,
            "status": "queued",
            "progress": 0,
            "stage": "queued",
        }
    return task_id


def _analysis_response(record: dict, cached: bool) -> dict:
    chords = db.chords_of(record)
    simple = db.chords_of(record, key="chords_simple")
    if not simple:  # 旧记录兜底：即时由完整标记推导
        _full, simple = postprocess(chords)
    beats = db.chords_of(record, key="beats")  # 复用 JSON 解析（列表）
    return {
        "id": record["id"],
        "filename": record["filename"],
        "audio_url": f"/api/audio/{record['stored_name']}",
        "duration": record["duration"],
        "chords": chords,
        "chords_simple": simple,
        "source": record["source"],
        "engine": record.get("engine", "auto"),
        "bpm": record.get("bpm"),
        "beats_count": len(beats),
        "edited": bool(record.get("edited")),
        "edited_at": record.get("edited_at"),
        "cached": cached,
        "created_at": record.get("created_at", ""),
    }


def _history_item(record: dict) -> dict:
    return {
        "id": record["id"],
        "filename": record["filename"],
        "duration": record["duration"],
        "source": record["source"],
        "engine": record.get("engine", "auto"),
        "bpm": record.get("bpm"),
        "chords_count": len(db.chords_of(record)),
        "edited": bool(record.get("edited")),
        "created_at": record["created_at"],
    }


ENGINES = {"auto", "deepchroma", "chordino"}


def _validate_engine(engine: str) -> str:
    engine = (engine or "auto").strip().lower()
    if engine not in ENGINES:
        raise HTTPException(status_code=422, detail=f"未知引擎「{engine}」")
    return engine


# ── 接口 ──────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "app": "chord-recognition"}


@app.post("/api/analyze")
def analyze(file: UploadFile = File(...), engine: str = Form("auto")):
    """接收音频文件：(md5, engine) 命中缓存直接返回，否则分析并入缓存。"""
    engine = _validate_engine(engine)
    filename = file.filename or "audio"
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的音频格式「{ext or '未知'}」，支持 wav / mp3 / ogg / flac / m4a / aac / webm / opus",
        )

    # 1) 先写入临时文件并计算 MD5，随后以 md5 命名资源副本（多引擎共享同一份音频）
    tmp = RESOURCES_DIR / f"tmp-{uuid.uuid4().hex[:12]}{ext}"
    try:
        md5, file_size = _save_and_hash(file.file, tmp)
    except ValueError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        tmp.unlink(missing_ok=True)
        logger.error("保存上传文件失败: %s", exc)
        raise HTTPException(status_code=500, detail="保存音频文件失败") from exc

    dest = RESOURCES_DIR / f"{md5}{ext}"
    if not dest.is_file():
        os.replace(tmp, dest)
    else:
        tmp.unlink(missing_ok=True)

    # 2) (md5, engine) 缓存命中？
    existing = db.find_by_md5(md5, engine)
    if existing:
        logger.info("缓存命中: %s (md5=%s, engine=%s)", existing["filename"], md5, engine)
        return _analysis_response(existing, cached=True)

    record = {
        "id": uuid.uuid4().hex[:12],
        "md5": md5,
        "filename": filename,
        "stored_name": dest.name,
        "file_size": file_size,
        "duration": get_duration(str(dest)),
        "source": "",
        "engine": engine,
        "chords": [],
        "chords_simple": [],
        "bpm": None,
        "beats": [],
    }

    # 长音频走后台任务，避免请求线程长时间占用；短音频保持原有同步 API。
    if (record["duration"] or 0) >= ASYNC_DURATION_SECONDS:
        task_id = _new_task()
        _executor.submit(_run_analyze_task, task_id, record, dest)
        return JSONResponse(
            status_code=202,
            content={"task_id": task_id, "status": "queued", "progress": 0,
                     "stage": "queued", "filename": filename},
        )

    try:
        record = _analyze_record(record, dest)
        db.insert(record)
    except sqlite3.IntegrityError:
        # 并发上传了同一文件：丢弃本次结果，返回已存在记录
        existing = db.find_by_md5(md5, engine)
        if existing:
            return _analysis_response(existing, cached=True)
        raise

    # 回读完整行（含 created_at 等数据库生成的字段）
    except Exception as exc:  # noqa: BLE001
        logger.error("和弦识别失败: %s", exc)
        raise HTTPException(status_code=422, detail=f"和弦识别失败：{exc}") from exc
    return _analysis_response(db.find_by_id(record["id"]), cached=False)


@app.get("/api/analyses/{rid}")
def get_analysis(rid: str):
    """按 ID 取回历史分析结果（历史记录点击进入）。"""
    record = db.find_by_id(rid)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    if not (RESOURCES_DIR / record["stored_name"]).is_file():
        raise HTTPException(status_code=404, detail="缓存音频文件已不存在")
    return _analysis_response(record, cached=True)


@app.post("/api/analyses/{rid}/reanalyze")
def reanalyze(rid: str, engine: str = Query("auto")):
    """对历史记录指向的资源音频重新执行和弦识别。

    engine 与记录原引擎不同时，为该 (md5, engine) 组合新建/更新独立缓存条目
    （同一音频的不同引擎版本在历史中各占一条，便于对比）。
    """
    engine = _validate_engine(engine)
    record = db.find_by_id(rid)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    audio_path = RESOURCES_DIR / record["stored_name"]
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="缓存音频文件已不存在，无法重新识别")

    duration = get_duration(str(audio_path))

    if (duration or 0) >= ASYNC_DURATION_SECONDS:
        task_id = _new_task()
        _executor.submit(_run_reanalyze_task, task_id, rid, engine, record, audio_path)
        return JSONResponse(
            status_code=202,
            content={"task_id": task_id, "status": "queued", "progress": 0,
                     "stage": "queued", "filename": record["filename"]},
        )

    logger.info("重新识别: %s (engine=%s)", record["filename"], engine)
    try:
        changes, source = extract_chords(str(audio_path), engine)
        chords_full, chords_simple = postprocess(changes)
    except Exception as exc:  # noqa: BLE001
        logger.error("重新识别失败: %s", exc)
        raise HTTPException(status_code=422, detail=f"和弦识别失败：{exc}") from exc

    # 同一 (md5, engine) 已有条目 → 更新；否则新建（保留原文件的存储与元数据）
    slot = db.find_by_md5(record["md5"], engine)
    if slot:
        target_id = slot["id"]
        db.update_analysis(
            target_id,
            chords=chords_full,
            chords_simple=chords_simple,
            source=source,
            duration=duration,
        )
    else:
        target_id = uuid.uuid4().hex[:12]
        db.insert(
            {
                "id": target_id,
                "md5": record["md5"],
                "filename": record["filename"],
                "stored_name": record["stored_name"],
                "file_size": record["file_size"],
                "duration": duration,
                "source": source,
                "engine": engine,
                "chords": chords_full,
                "chords_simple": chords_simple,
            }
        )
    db.clear_edited(target_id)  # 机器结果覆盖人工编辑标记
    return _analysis_response(db.find_by_id(target_id), cached=False)


@app.get("/api/tasks/{task_id}")
def get_task(task_id: str):
    """查询后台分析任务状态；完成时 result 字段包含标准分析响应。"""
    return _task_response(task_id)


@app.get("/api/analyses/{rid}/beats")
def get_beats(rid: str):
    """节拍网格数据：已缓存直接返回，否则按需计算并入库（旧记录回填）。"""
    record = db.find_by_id(rid)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    beats = db.chords_of(record, key="beats")
    if record.get("bpm") is not None and beats:
        return {"bpm": record["bpm"], "beats": beats, "source": "cached", "cached": True}

    audio_path = RESOURCES_DIR / record["stored_name"]
    if not audio_path.is_file():
        raise HTTPException(status_code=404, detail="缓存音频文件已不存在，无法识别节拍")

    logger.info("按需识别节拍: %s", record["filename"])
    bpm, beats, source = extract_beats(str(audio_path))
    if beats:
        db.update_beats(rid, bpm, beats)
    return {"bpm": bpm, "beats": beats, "source": source, "cached": False}


@app.put("/api/analyses/{rid}/chords")
def put_chords(rid: str, payload: dict = Body(default=None)):
    """人工编辑保存：写回完整档，重推简化档，置「已编辑」标记。"""
    if payload is None:
        raise HTTPException(status_code=422, detail="缺少请求体")
    chords = payload.get("chords")
    if not isinstance(chords, list) or not chords:
        raise HTTPException(status_code=422, detail="chords 需为非空数组")

    record = db.find_by_id(rid)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")

    # 防御性规范化：结构/类型/排序/夹取
    duration = record.get("duration") or get_duration(
        str(RESOURCES_DIR / record["stored_name"])
    )
    cleaned = []
    for item in chords:
        if not isinstance(item, dict):
            raise HTTPException(status_code=422, detail="chords 元素需为对象")
        ts = item.get("timestamp")
        label = item.get("chord")
        try:
            ts = round(float(ts), 3)
        except (TypeError, ValueError):
            raise HTTPException(status_code=422, detail="timestamp 需为数字") from None
        if not isinstance(label, str) or not label.strip():
            raise HTTPException(status_code=422, detail="chord 需为非空字符串")
        cleaned.append({"timestamp": ts, "chord": label.strip()})

    cleaned.sort(key=lambda c: c["timestamp"])
    lo = 0.0
    hi = duration if isinstance(duration, (int, float)) and duration > 0 else None
    for c in cleaned:
        c["timestamp"] = max(lo, c["timestamp"])
        if hi is not None:
            c["timestamp"] = min(hi, c["timestamp"])
        lo = c["timestamp"]

    # 编辑保存：完整档原样保留（不做时间合并，尊重用户编辑）；
    # 简化档仅做标签归一化 + 折叠相邻同名，不删任何用户边界
    chords_full = cleaned
    chords_simple = collapse_duplicates(
        [
            {"timestamp": c["timestamp"], "chord": simplify_chord(c["chord"])}
            for c in cleaned
        ]
    )
    db.mark_edited(rid, chords_full, chords_simple)
    logger.info("人工编辑已保存: %s (%s 条)", record["filename"], len(chords_full))
    return _analysis_response(db.find_by_id(rid), cached=False)


@app.delete("/api/analyses/{rid}")
def delete_analysis(rid: str):
    """删除历史记录；仅当无其他记录引用同一音频时才删除资源文件。"""
    record = db.find_by_id(rid)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在")
    refs = db.count_by_stored(record["stored_name"])
    db.delete_by_id(rid)
    if refs <= 1:  # 本条是唯一引用 → 音频文件一并清理
        (RESOURCES_DIR / record["stored_name"]).unlink(missing_ok=True)
    logger.info("已删除记录: %s (%s)", record["filename"], rid)
    return {"deleted": True, "id": rid}


@app.get("/api/history")
def history():
    """历史记录列表（按时间倒序）。"""
    return [_history_item(r) for r in db.list_all()]


@app.get("/api/audio/{name}")
def audio(name: str):
    """返回资源目录中的音频文件，供 <audio> 播放。"""
    target = (RESOURCES_DIR / name).resolve()
    if RESOURCES_DIR.resolve() not in target.parents or not target.is_file():
        raise HTTPException(status_code=404, detail="音频不存在")
    return FileResponse(target)


# 生产模式：托管前端构建产物（需先执行 npm run build）
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=False)
