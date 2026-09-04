"""SQLite 持久层：缓存索引与历史记录。

表 analyses 以 (md5, engine) 为唯一键（同一音频、不同识别引擎各自缓存）；
chords 列为「完整」标记（合并短段后），chords_simple 列为「简化」标记。
音频文件本体存放在 backend/resources/ 目录（见 main.py）。
"""
import json
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "analyses.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    id            TEXT PRIMARY KEY,
    md5           TEXT NOT NULL,
    filename      TEXT NOT NULL,
    stored_name   TEXT NOT NULL,
    file_size     INTEGER NOT NULL DEFAULT 0,
    duration      REAL,
    source        TEXT NOT NULL DEFAULT '',
    chords        TEXT NOT NULL,
    chords_simple TEXT NOT NULL DEFAULT '',
    engine        TEXT NOT NULL DEFAULT 'chordino',
    bpm           REAL DEFAULT NULL,
    beats         TEXT DEFAULT NULL,
    key_name      TEXT DEFAULT NULL,
    key_short     TEXT DEFAULT NULL,
    key_confidence REAL DEFAULT NULL,
    key_method    TEXT DEFAULT NULL,
    edited        INTEGER NOT NULL DEFAULT 0,
    edited_at     TEXT DEFAULT NULL,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (md5, engine)
);
"""


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _columns(conn) -> set:
    return {r[1] for r in conn.execute("PRAGMA table_info(analyses)")}


def init_db():
    with closing(_connect()) as conn, conn:
        conn.execute(SCHEMA)
        cols = _columns(conn)
        if "engine" not in cols:
            # 旧库迁移：重建表（补 engine 列，唯一键改为 md5+engine）
            conn.execute("ALTER TABLE analyses RENAME TO analyses_old")
            conn.execute(SCHEMA)
            conn.execute(
                """
                INSERT INTO analyses
                    (id, md5, filename, stored_name, file_size, duration,
                     source, chords, chords_simple, engine, created_at)
                SELECT id, md5, filename, stored_name, file_size, duration,
                       source, chords, chords_simple, 'chordino', created_at
                FROM analyses_old
                """
            )
            conn.execute("DROP TABLE analyses_old")
        # 编辑工作台 / 节拍识别新增列（幂等）
        additions = {
            "bpm": "REAL DEFAULT NULL",
            "beats": "TEXT DEFAULT NULL",
            "key_name": "TEXT DEFAULT NULL",
            "key_short": "TEXT DEFAULT NULL",
            "key_confidence": "REAL DEFAULT NULL",
            "key_method": "TEXT DEFAULT NULL",
            "edited": "INTEGER NOT NULL DEFAULT 0",
            "edited_at": "TEXT DEFAULT NULL",
        }
        for name, decl in additions.items():
            if name not in _columns(conn):
                conn.execute(f"ALTER TABLE analyses ADD COLUMN {name} {decl}")


def find_by_md5(md5: str, engine: str = "auto"):
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE md5 = ? AND engine = ?",
            (md5, engine),
        ).fetchone()
    return dict(row) if row else None


def find_by_id(rid: str):
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE id = ?", (rid,)
        ).fetchone()
    return dict(row) if row else None


def insert(record: dict):
    """插入一条分析记录；chords / chords_simple / beats 需为可 JSON 序列化对象。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            INSERT INTO analyses
                (id, md5, filename, stored_name, file_size, duration, source,
                chords, chords_simple, engine, bpm, beats,
                key_name, key_short, key_confidence, key_method)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record["id"],
                record["md5"],
                record["filename"],
                record["stored_name"],
                record["file_size"],
                record["duration"],
                record["source"],
                json.dumps(record["chords"], ensure_ascii=False),
                json.dumps(record.get("chords_simple") or [], ensure_ascii=False),
                record.get("engine") or "auto",
                record.get("bpm"),
                json.dumps(record.get("beats") or [], ensure_ascii=False)
                if record.get("beats")
                else None,
                record.get("key_name"),
                record.get("key_short"),
                record.get("key_confidence"),
                record.get("key_method"),
            ),
        )


def update_simple(rid: str, chords_simple: list):
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE analyses SET chords_simple = ? WHERE id = ?",
            (json.dumps(chords_simple, ensure_ascii=False), rid),
        )


def update_full(rid: str, chords_full: list):
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE analyses SET chords = ? WHERE id = ?",
            (json.dumps(chords_full, ensure_ascii=False), rid),
        )


def update_analysis(rid: str, *, chords: list, chords_simple: list,
                    source: str, duration, key_data: dict | None = None):
    """重新识别后整行更新（created_at 刷新为当前时间，历史排序随之更新）。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            UPDATE analyses
            SET chords = ?, chords_simple = ?, source = ?, duration = ?,
                key_name = ?, key_short = ?, key_confidence = ?, key_method = ?,
                created_at = datetime('now')
            WHERE id = ?
            """,
            (
                json.dumps(chords, ensure_ascii=False),
                json.dumps(chords_simple, ensure_ascii=False),
                source,
                duration,
                (key_data or {}).get("key"),
                (key_data or {}).get("key_short"),
                (key_data or {}).get("key_confidence"),
                (key_data or {}).get("key_method"),
                rid,
            ),
        )


def update_key(rid: str, key_data: dict):
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            UPDATE analyses
            SET key_name = ?, key_short = ?, key_confidence = ?, key_method = ?
            WHERE id = ?
            """,
            (
                key_data.get("key"),
                key_data.get("key_short"),
                key_data.get("key_confidence"),
                key_data.get("key_method"),
                rid,
            ),
        )


def delete_by_id(rid: str):
    with closing(_connect()) as conn, conn:
        conn.execute("DELETE FROM analyses WHERE id = ?", (rid,))


def update_beats(rid: str, bpm, beats: list):
    """节拍识别结果入库（幂等；已有值不覆盖由调用方保证）。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE analyses SET bpm = ?, beats = ? WHERE id = ?",
            (bpm, json.dumps(beats, ensure_ascii=False) if beats else None, rid),
        )


def mark_edited(rid: str, chords: list, chords_simple: list):
    """人工编辑保存：写两档并置 edited 标记。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            UPDATE analyses
            SET chords = ?, chords_simple = ?, edited = 1,
                edited_at = datetime('now')
            WHERE id = ?
            """,
            (
                json.dumps(chords, ensure_ascii=False),
                json.dumps(chords_simple, ensure_ascii=False),
                rid,
            ),
        )


def clear_edited(rid: str):
    """重新识别后清除人工编辑标记（两档已由调用方更新）。"""
    with closing(_connect()) as conn, conn:
        conn.execute(
            "UPDATE analyses SET edited = 0, edited_at = NULL WHERE id = ?",
            (rid,),
        )


def count_by_stored(stored_name: str) -> int:
    """引用同一资源文件的记录数（多个引擎共享一份音频时 > 1）。"""
    with closing(_connect()) as conn, conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM analyses WHERE stored_name = ?",
            (stored_name,),
        ).fetchone()
    return int(row[0]) if row else 0


def list_all():
    with closing(_connect()) as conn, conn:
        rows = conn.execute(
            "SELECT * FROM analyses ORDER BY created_at DESC, rowid DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def chords_of(record: dict, key: str = "chords") -> list:
    """把记录中的 JSON 列还原为列表。"""
    try:
        data = json.loads(record.get(key) or "[]")
        return data if isinstance(data, list) else []
    except (TypeError, ValueError):
        return []
