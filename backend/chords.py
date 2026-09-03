"""和弦提取模块。

引擎：
    * deepchroma —— madmom-infer 的 DeepChroma（DNN 色度）+ CRF，
      精度最高的本地方案；权重首次运行时下载（存 backend/.model_cache）
    * chordino   —— Chordino (NNLS-Chroma)，传统方案
    * lv-chordia  —— 独立 .venv-lv 中的可选大词汇模型
    * 自动回退     —— 任一引擎失败时降级：deepchroma → chordino → librosa 模板

结果会经过后处理（见 postprocess）：合并过短片段、折叠重复标记、
并按「简化 / 完整」两档归一化和弦名。
"""
import json
import logging
import os
import re
import subprocess
from pathlib import Path

os.environ.setdefault("VAMP_PATH", os.path.expanduser("~/vamp-plugins"))
# madmom-infer 权重缓存放到项目内（本机 ~/.cache 不可写）
os.environ.setdefault(
    "XDG_CACHE_HOME", str(Path(__file__).resolve().parent / ".model_cache")
)

logger = logging.getLogger("chords")

# 黑键统一用降号命名，与 Chordino 输出保持一致
NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]

_TEMPLATES = None

# ── 和弦名简化 ──────────────────────────────────────────────

# 根音 + 后缀（如 "Bb6" → root="Bb", suffix="6"；"D/F#" → root="D", suffix="/F#"）
_CHORD_RE = re.compile(r"^([A-G](?:#|b)?)(.*)$")

# 保留原样的后缀（音乐上常见、信息量大）
_KEEP_SUFFIX = {
    "", "m", "7", "maj7", "m7", "m7b5", "dim", "dim7", "aug",
    "sus2", "sus4", "5",
}


def simplify_chord(label: str) -> str:
    """把复杂和弦名归一化为「根音 + 常见性质」。

    去掉转位低音（D/F# → D）、六/九/挂留扩展（Bb6 → Bb）、
    以及罕见的七和弦变体（C7b9 → C7）；保留 maj7 / m7 / dim / sus 等。
    """
    label = (label or "").strip()
    if not label or label == "N":
        return label
    m = _CHORD_RE.match(label)
    if not m:
        return label
    root, suffix = m.group(1), m.group(2)
    if suffix in _KEEP_SUFFIX:
        return label
    if suffix.startswith("maj7"):  # maj7b5 等
        return root + "maj7"
    if suffix.startswith("m7"):  # m7b5 / m7b9 等
        return root + "m7"
    if suffix.startswith("m"):  # m6 / m9 等
        return root + "m"
    if suffix.startswith("7"):  # 7b9 / 7#11 等
        return root + "7"
    return root  # 6 / 9 / add9 / 11 / 13 / 69 …一律归为大三和弦


def merge_short_segments(changes: list, min_dur: float = 0.6) -> list:
    """把持续时间短于 min_dur 秒的片段并入前一片段（抑制抖动的分段）。"""
    if not changes:
        return []
    merged = [dict(changes[0])]
    for i in range(1, len(changes)):
        dur = changes[i]["timestamp"] - changes[i - 1]["timestamp"]
        if dur < min_dur:
            continue  # 并入前一段
        merged.append(dict(changes[i]))
    return merged


def collapse_duplicates(changes: list) -> list:
    """折叠相邻的相同和弦标记。"""
    out = []
    for c in changes:
        if out and out[-1]["chord"] == c["chord"]:
            continue
        out.append(c)
    return out


def postprocess(changes: list, min_dur: float = 0.6):
    """后处理管线：合并短段 → 折叠重复 → 生成「完整」与「简化」两档。

    返回 (chords_full, chords_simple)。
    """
    full = collapse_duplicates(merge_short_segments(changes, min_dur))
    simple = collapse_duplicates(
        [
            {"timestamp": c["timestamp"], "chord": simplify_chord(c["chord"])}
            for c in full
        ]
    )
    return full, simple


def _build_templates():
    """构建色度模板库（大三/小三/减三/增三/sus2/sus4 + 七和弦）。"""
    global _TEMPLATES
    if _TEMPLATES is not None:
        return _TEMPLATES
    import numpy as np

    templates = {}
    kinds = {
        "": [0, 4, 7],
        "m": [0, 3, 7],
        "dim": [0, 3, 6],
        "aug": [0, 4, 8],
        "sus2": [0, 2, 7],
        "sus4": [0, 5, 7],
        "7": [0, 4, 7, 10],
        "maj7": [0, 4, 7, 11],
        "m7": [0, 3, 7, 10],
        "m7b5": [0, 3, 6, 10],
    }
    for suffix, intervals in kinds.items():
        for i, name in enumerate(NOTE_NAMES):
            vec = np.zeros(12)
            for iv in intervals:
                vec[(i + iv) % 12] += 1.0
            vec /= np.linalg.norm(vec) + 1e-9
            templates[f"{name}{suffix}"] = vec
    _TEMPLATES = templates
    return templates


def extract_chords(audio_path: str, engine: str = "auto"):
    """提取和弦序列，返回 (chords, source)。

    engine: "auto" | "deepchroma" | "chordino" | "lv-chordia"
    chords: [{"timestamp": float(秒), "chord": str}, ...]，按时间升序。
    source: 实际使用的提取器（"deepchroma" / "chordino" / "lv-chordia" / "chroma-template"）。
    """
    if engine == "deepchroma":
        try:
            return _extract_deepchroma(audio_path), "deepchroma"
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepChroma 提取失败（%s），回退 Chordino", exc)
            try:
                return _extract_chordino(audio_path), "chordino"
            except Exception as exc2:  # noqa: BLE001
                logger.warning("Chordino 提取失败（%s），回退 librosa 模板", exc2)
                return _extract_librosa(audio_path), "chroma-template"

    if engine == "chordino":
        try:
            return _extract_chordino(audio_path), "chordino"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Chordino 提取失败（%s），回退 librosa 模板", exc)
            return _extract_librosa(audio_path), "chroma-template"

    if engine == "lv-chordia":
        return _extract_lv_chordia(audio_path), "lv-chordia"

    # auto：高精度优先
    try:
        return _extract_deepchroma(audio_path), "deepchroma"
    except Exception as exc:  # noqa: BLE001
        logger.warning("DeepChroma 提取失败（%s），回退 Chordino", exc)
        try:
            return _extract_chordino(audio_path), "chordino"
        except Exception as exc2:  # noqa: BLE001
            logger.warning("Chordino 提取失败（%s），回退 librosa 模板", exc2)
            return _extract_librosa(audio_path), "chroma-template"


# 升号 → 降号约定（与 Chordino 输出保持一致；F# 维持升号）
_SHARP_TO_FLAT = {"C#": "Db", "D#": "Eb", "F#": "F#", "G#": "Ab", "A#": "Bb"}


def _harte_to_shorthand(label: str) -> str:
    """Harte 语法转简写：C:maj → C；A#:min → Bbm（统一降号）；N → N。"""
    if not label or label == "N":
        return "N"
    if ":" in label:
        root, quality = label.split(":", 1)
        root = _SHARP_TO_FLAT.get(root, root)
        if quality == "maj":
            return root
        if quality == "min":
            return root + "m"
        return root + quality
    return label


def _extract_deepchroma(audio_path: str):
    """madmom-infer：DeepChroma（DNN 色度）→ CRF → 分段。"""
    from madmom_infer.api import MadmomAnalyzer

    analyzer = MadmomAnalyzer(tasks=("chords",))
    segments = analyzer(audio_path)["chords"]
    out = [
        {
            "timestamp": round(float(seg["start"]), 3),
            "chord": _harte_to_shorthand(seg["label"]),
        }
        for seg in segments
    ]
    if not out:
        raise RuntimeError("DeepChroma 未返回任何和弦")
    return out


def _extract_chordino(audio_path: str):
    from chord_extractor.extractors import Chordino, TuningMode

    # 参数对应 Chordino 插件（vamp-plugin-pack）：useNNLS / rollon /
    # tuningmode / whitening / s / boostn / usehartesyntax（无 smoothing）
    chordino = Chordino(
        use_nnls=True,
        roll_on=1,
        tuning_mode=TuningMode.GLOBAL,
        spectral_whitening=1,
        spectral_shape=0.7,
        boost_n_likelihood=0.1,
    )
    changes = chordino.extract(audio_path)
    if not changes:
        raise RuntimeError("Chordino 未返回任何和弦")
    return [
        {"timestamp": round(float(c.timestamp), 3), "chord": c.chord}
        for c in changes
    ]


def _extract_lv_chordia(audio_path: str):
    """Call the optional lv-chordia adapter in the isolated environment."""
    root = Path(__file__).resolve().parents[1]
    python = Path(
        os.getenv("CHORD_LV_PYTHON", str(root / ".venv-lv" / "bin" / "python"))
    ).expanduser()
    adapter = root / "experiments" / "lv_chordia_adapter.py"
    if not python.is_file():
        raise RuntimeError(f"lv-chordia 环境不存在：{python}")
    if not adapter.is_file():
        raise RuntimeError(f"lv-chordia 适配器不存在：{adapter}")

    device = os.getenv("CHORD_LV_DEVICE", "cpu").strip().lower()
    if device not in {"cpu", "mps"}:
        raise RuntimeError(f"CHORD_LV_DEVICE 必须是 cpu 或 mps，而不是 {device!r}")
    vocabulary = os.getenv("CHORD_LV_VOCABULARY", "submission").strip().lower()
    if vocabulary not in {"submission", "ismir2017", "full"}:
        raise RuntimeError(f"CHORD_LV_VOCABULARY 不支持：{vocabulary!r}")
    try:
        result = subprocess.run(
            [
                str(python),
                str(adapter),
                str(Path(audio_path).resolve()),
                "--device",
                device,
                "--vocabulary",
                vocabulary,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=float(os.getenv("CHORD_LV_TIMEOUT_SECONDS", "3600")),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"lv-chordia 超时（{exc.timeout} 秒）") from exc
    if result.returncode:
        detail = result.stderr.strip()[-4000:]
        raise RuntimeError(detail or f"lv-chordia 进程退出码 {result.returncode}")
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("lv-chordia 返回了无效 JSON") from exc
    if payload.get("error"):
        raise RuntimeError(str(payload["error"]))
    changes = payload.get("chords") or []
    if not changes:
        raise RuntimeError("lv-chordia 未返回任何和弦")
    return [
        {"timestamp": round(float(item["timestamp"]), 3), "chord": item["chord"]}
        for item in changes
    ]


def _extract_librosa(audio_path: str, min_sec: float = 0.25):
    import numpy as np
    from scipy.ndimage import median_filter

    import librosa

    y, sr = librosa.load(audio_path, sr=22050, mono=True)
    if y.size == 0:
        raise RuntimeError("音频内容为空")

    hop = 512
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop)
    chroma /= np.linalg.norm(chroma, axis=0, keepdims=True) + 1e-9

    templates = _build_templates()
    names = list(templates.keys())
    matrix = np.stack([templates[n] for n in names])  # (K, 12)
    best = np.argmax(matrix @ chroma, axis=0)  # (T,)

    # 中值滤波平滑（窗口约 0.5s），抑制抖动
    t_per_frame = hop / sr
    win = max(3, int(round(0.5 / t_per_frame)))
    win = win if win % 2 == 1 else win + 1
    smoothed = median_filter(best, size=win)

    # 合并连续同值帧
    segments = []  # (start_frame, end_frame, chord_index)
    start = 0
    for i in range(1, smoothed.size + 1):
        if i == smoothed.size or smoothed[i] != smoothed[start]:
            segments.append((start, i - 1, int(smoothed[start])))
            start = i

    # 过短片段并入前一段
    min_frames = max(1, int(min_sec / t_per_frame))
    merged = []
    for s, e, idx in segments:
        if merged and (e - s + 1) < min_frames:
            merged[-1] = (merged[-1][0], e, merged[-1][2])
        else:
            merged.append((s, e, idx))

    return [
        {"timestamp": round(s * t_per_frame, 3), "chord": names[idx]}
        for s, _e, idx in merged
    ]


def get_duration(audio_path: str):
    """读取音频时长（秒），失败时返回 None。"""
    try:
        import soundfile as sf

        return round(sf.info(audio_path).duration, 3)
    except Exception:  # noqa: BLE001
        pass
    try:
        import librosa

        return round(librosa.get_duration(filename=audio_path), 3)
    except Exception:  # noqa: BLE001
        return None


def extract_beats(audio_path: str):
    """节拍识别，返回 (bpm, beats, source)。

    beats: [float(秒), ...] 逐拍时刻；source: "librosa" | "madmom" | "none"。
    策略：librosa 快速路径优先（对稳定节拍的流行乐足够且仅需数秒）；
    librosa 无结果时回退 madmom RNN 节拍（较重，仅困难音频触发）。
    任何失败均容错返回，不阻断主流程。
    """
    # 1) librosa 快速路径
    try:
        import librosa

        y, sr = librosa.load(audio_path, sr=22050, mono=True)
        tempo, frames = librosa.beat.beat_track(y=y, sr=sr)
        bpm = round(float(tempo)) if tempo and float(tempo) > 0 else None
        beats = [round(float(t), 3) for t in librosa.frames_to_time(frames, sr=sr)]
        if beats:
            return bpm, beats, "librosa"
        logger.warning("librosa 节拍为空，回退 madmom")
    except Exception as exc:  # noqa: BLE001
        logger.warning("librosa 节拍识别失败（%s），回退 madmom", exc)

    # 2) madmom RNN 节拍兜底（不请求 tempo 任务——其处理器组合有缺陷）
    try:
        from madmom_infer.api import MadmomAnalyzer

        import numpy as np

        analyzer = MadmomAnalyzer(tasks=("beats",))
        beats = [float(b) for b in analyzer(audio_path)["beats"]]
        if beats:
            arr = np.asarray(beats, dtype=float)
            med = float(np.median(np.diff(arr)))
            bpm = round(60.0 / med) if med > 0 else None
            return bpm, [round(b, 3) for b in beats], "madmom"
    except Exception as exc:  # noqa: BLE001
        logger.warning("madmom 节拍识别失败: %s", exc)

    return None, [], "none"
