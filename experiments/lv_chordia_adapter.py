#!/usr/bin/env python3
"""Run lv-chordia in its isolated environment and emit one JSON document."""

import argparse
import importlib
import json
import platform
import re
import resource
import sys
import time
from pathlib import Path


_SHARP_TO_FLAT = {"C#": "Db", "D#": "Eb", "F#": "F#", "G#": "Ab", "A#": "Bb"}
_DEGREE_INTERVALS = {
    "1": 0, "b2": 1, "2": 2, "b3": 3, "3": 4, "4": 5,
    "b5": 6, "5": 7, "#5": 8, "b6": 8, "6": 9, "b7": 10,
    "7": 11,
}
_NOTE_NAMES = ["C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B"]
_KEEP_SUFFIXES = {"", "m", "7", "maj7", "m7", "m7b5", "dim", "dim7", "aug", "sus2", "sus4", "5"}


def _normalize_note(note: str) -> str:
    return _SHARP_TO_FLAT.get(note, note)


def _bass_note(root: str, bass: str) -> str:
    bass = bass.strip()
    if re.fullmatch(r"[A-G](?:#|b)?", bass):
        return _normalize_note(bass)
    interval = _DEGREE_INTERVALS.get(bass)
    if interval is None:
        return bass
    root_index = _NOTE_NAMES.index(_normalize_note(root))
    return _NOTE_NAMES[(root_index + interval) % 12]


def harte_to_shorthand(label: str) -> str:
    """Convert Harte/MIREX labels, including package degree basses."""
    label = (label or "").strip()
    if not label or label in {"N", "X"}:
        return "N"
    match = re.fullmatch(r"([A-G](?:#|b)?)(?::([^/]+))?(?:/(.+))?", label)
    if not match:
        return label
    root, quality, bass = match.groups()
    root = _normalize_note(root)
    quality = quality or ""
    if quality == "maj":
        suffix = ""
    elif quality.startswith("min"):
        suffix = "m" + quality[3:]
    else:
        suffix = quality
    result = root + suffix
    if bass:
        result += "/" + _bass_note(root, bass)
    return result


def simplify_chord(label: str) -> str:
    """Keep the project's common suffixes while dropping bass/rare extensions."""
    if label in {"", "N"}:
        return label
    match = re.fullmatch(r"([A-G](?:#|b)?)(.*)", label)
    if not match:
        return label
    root, suffix = match.groups()
    if suffix.startswith("/"):
        suffix = ""
    if suffix in _KEEP_SUFFIXES:
        return root + suffix
    if suffix.startswith("maj7"):
        return root + "maj7"
    if suffix.startswith("m7"):
        return root + "m7"
    if suffix.startswith("m"):
        return root + "m"
    if suffix.startswith("7"):
        return root + "7"
    return root


def _peak_memory_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # macOS reports bytes; Linux reports KiB.
    value = value if sys.platform == "darwin" else value * 1024
    return round(value / (1024 * 1024), 1)


def _enable_mps_bridge(torch) -> None:
    """Bridge this release's CUDA-only calls to MPS inside this process."""
    from torch import nn

    if not torch.backends.mps.is_available():
        raise RuntimeError("MPS is not available in this PyTorch installation")

    # ponytail: package 1.1.0 has CUDA-only calls; keep the bridge local to this subprocess.
    torch.cuda.device_count = lambda: 1
    torch.Tensor.cuda = lambda self, device=None, non_blocking=False: self.to("mps")
    nn.Module.cuda = lambda self, device=None: self.to("mps")
    original_load = torch.load

    def load(*args, **kwargs):
        if kwargs.get("map_location") == "cuda":
            kwargs["map_location"] = "mps"
        return original_load(*args, **kwargs)

    torch.load = load


def _energy_onset(audio: Path, sr: int = 22050, hop_length: int = 512) -> tuple[int, float | None]:
    """Find the first short run of clearly non-silent frames."""
    import librosa
    import numpy as np

    y, _ = librosa.load(str(audio.resolve()), sr=sr, mono=True)
    if y.size == 0:
        return 0, None
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop_length, center=True)[0]
    threshold = max(float(rms.max()) * 0.05, 1e-4)
    active = rms > threshold
    consecutive = np.convolve(active.astype(np.int8), np.ones(3, dtype=np.int8), mode="valid")
    frames = np.flatnonzero(consecutive >= 3)
    if not frames.size:
        return 0, None
    frame = int(frames[0])
    return frame, round(frame * hop_length / sr, 3)


def _energy_aware_decode(start_frame: int, suppress_n_until: int):
    """Start chord search at the active onset and avoid the false N prefix."""
    import numpy as np

    def decode(self, prob_list, beat_arr, triad_restriction=None):
        result_names, result_logprob = self.get_chord_tag_obs(prob_list, triad_restriction)
        n_frame, n_chord = result_logprob.shape
        if not n_frame:
            return []
        start = min(max(start_frame, 0), n_frame - 1)
        active_end = min(max(suppress_n_until, start), n_frame - 1)
        result_logprob = result_logprob.copy()
        result_logprob[start : active_end + 1, 0] = -np.inf
        dp = np.zeros_like(result_logprob)
        dp[start, :] = result_logprob[start, :]
        dp_max_at = np.zeros(n_frame, dtype=int)
        pre = np.zeros_like(result_logprob, dtype=int)
        dp_max_at[start] = np.argmax(dp[start, :])
        pre[start, :] = -1
        for t in range(start + 1, n_frame):
            same_trans = dp[t - 1, :]
            if beat_arr[t]:
                diff_trans = dp[t - 1, dp_max_at[t - 1]] - (
                    self.diff_trans_penalty
                    if beat_arr[t] == 1
                    else self.beat_trans_penalty[beat_arr[t] - 2]
                )
                use_same_trans = same_trans > diff_trans
                dp[t, :] = np.maximum(diff_trans, same_trans) + result_logprob[t, :]
                pre[t, :] = dp_max_at[t - 1]
                pre[t, use_same_trans] = np.arange(n_chord)[use_same_trans]
            else:
                dp[t, :] = same_trans + result_logprob[t, :]
                pre[t, :] = np.arange(n_chord)
            dp_max_at[t] = np.argmax(dp[t, :])
        decode_ids = [0] * start + [None] * (n_frame - start)
        decode_ids[-1] = dp_max_at[-1]
        for t in range(n_frame - 2, start - 1, -1):
            decode_ids[t] = pre[t + 1, decode_ids[t + 1]]
        return [result_names[i] for i in decode_ids]

    return decode


def _leading_n_end(raw: list[dict]) -> float | None:
    if raw and raw[0].get("chord") == "N" and float(raw[0].get("start_time", 0)) <= 0.05:
        return float(raw[0]["end_time"])
    return None


def recognize(audio: Path, device: str, vocabulary: str) -> dict:
    import torch

    if device == "mps":
        _enable_mps_bridge(torch)

    recognition = importlib.import_module("lv_chordia.chord_recognition")
    load_seconds = 0.0
    original_init = recognition.NetworkInterface.__init__

    def timed_init(self, *args, **kwargs):
        nonlocal load_seconds
        started = time.perf_counter()
        try:
            return original_init(self, *args, **kwargs)
        finally:
            load_seconds += time.perf_counter() - started

    recognition.NetworkInterface.__init__ = timed_init
    onset_frame, onset_seconds = _energy_onset(audio)
    started = time.perf_counter()
    raw = recognition.chord_recognition(str(audio.resolve()), vocabulary)
    original_leading_n = _leading_n_end(raw)
    correction_applied = False
    if (
        original_leading_n is not None
        and onset_seconds is not None
        and original_leading_n - onset_seconds > 0.75
    ):
        print(
            f"Correcting leading N: energy starts at {onset_seconds:.2f}s, "
            f"original N ended at {original_leading_n:.2f}s",
            file=sys.stderr,
        )
        original_decode = recognition.XHMMDecoder.decode
        correction_end_frame = int(round(original_leading_n * 22050 / 512))
        recognition.XHMMDecoder.decode = _energy_aware_decode(onset_frame, correction_end_frame)
        try:
            raw = recognition.chord_recognition(str(audio.resolve()), vocabulary)
        finally:
            recognition.XHMMDecoder.decode = original_decode
        correction_applied = True
    elapsed = time.perf_counter() - started
    chords = [
        {
            "timestamp": item["start_time"],
            "end": item["end_time"],
            "raw_chord": item["chord"],
            "chord": harte_to_shorthand(item["chord"]),
            "simplified_chord": simplify_chord(harte_to_shorthand(item["chord"])),
        }
        for item in raw
    ]
    duration = round(float(raw[-1]["end_time"]) if raw else 0.0, 3)
    return {
        "engine": "lv-chordia",
        "device": device,
        "vocabulary": vocabulary,
        "machine": platform.machine(),
        "package_version": getattr(importlib.import_module("lv_chordia"), "__version__", None),
        "duration": duration,
        "load_seconds": round(load_seconds, 3),
        "inference_seconds": round(max(0.0, elapsed - load_seconds), 3),
        "elapsed_seconds": round(elapsed, 3),
        "realtime_factor": round(elapsed / duration, 4) if duration else None,
        "peak_memory_mb": _peak_memory_mb(),
        "energy_onset_seconds": onset_seconds,
        "original_leading_n_seconds": round(original_leading_n, 3) if original_leading_n is not None else None,
        "leading_n_correction_applied": correction_applied,
        "chord_count": len(chords),
        "unique_chords": sorted({item["chord"] for item in chords}),
        "chords": chords,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--device", choices=("cpu", "mps"), default="cpu")
    parser.add_argument("--vocabulary", "--chord-dict", dest="vocabulary", choices=("submission", "ismir2017", "full"), default="submission")
    args = parser.parse_args()
    if not args.audio.is_file():
        print(f"audio file not found: {args.audio}", file=sys.stderr)
        return 2
    try:
        json.dump(recognize(args.audio, args.device, args.vocabulary), sys.stdout, ensure_ascii=False, indent=2)
        print()
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"lv-chordia {args.device} failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
