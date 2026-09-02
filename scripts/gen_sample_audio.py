#!/usr/bin/env python3
"""生成一段合成的和弦进行示例音频（用于本地测试，无需真实歌曲）。

用法:
    uv run python scripts/gen_sample_audio.py [输出路径] [小节数]

默认生成 C → F → G → Am 四个和弦、每小节 3 秒的 12 秒 wav。
"""
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# 根音频率（A4 = 440Hz）
NOTE_FREQ = {
    "C": 261.63, "C#": 277.18, "D": 293.66, "D#": 311.13,
    "E": 329.63, "F": 349.23, "F#": 369.99, "G": 392.00,
    "G#": 415.30, "A": 440.00, "A#": 466.16, "B": 493.88,
}

PROGRESSION = [
    (["C", "E", "G"], 0),       # C
    (["F", "A", "C"], 0),       # F
    (["G", "B", "D"], 0),       # G
    (["A", "C", "E"], -12),     # Am（低八度）
]

SR = 22050


def chord_tone(root, octave):
    """根音+半音偏移 → 频率（Hz）"""
    idx = list(NOTE_FREQ).index(root)
    base = list(NOTE_FREQ.values())[idx]
    return base * (2 ** (octave / 12))


def render(duration, out_path, bars=4):
    total = int(SR * duration)
    y = np.zeros(total)
    chord_len = int(SR * duration / bars)

    for bar in range(bars):
        notes, octave = PROGRESSION[bar % len(PROGRESSION)]
        start = bar * chord_len
        end = start + chord_len
        # 每个音：基频 + 两个泛音，轻微包络避免爆音
        for i, n in enumerate(notes):
            f = chord_tone(n, octave if i == 2 else octave + 12)
            t = np.arange(end - start) / SR
            env = np.minimum(1.0, np.minimum(t / 0.02, (chord_len / SR - t) / 0.08))
            partial = (
                np.sin(2 * np.pi * f * t)
                + 0.5 * np.sin(2 * np.pi * 2 * f * t)
                + 0.25 * np.sin(2 * np.pi * 3 * f * t)
            )
            y[start:end] += 0.12 * env * partial

    sf.write(out_path, y, SR)
    print(f"已生成: {out_path}（{duration}s, {bars} 小节, {SR}Hz）")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "sample.wav"
    bars = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    duration = bars * 3.0
    render(duration, Path(out), bars)
