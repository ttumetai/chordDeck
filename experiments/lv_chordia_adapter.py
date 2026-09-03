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
    started = time.perf_counter()
    raw = recognition.chord_recognition(str(audio.resolve()), vocabulary)
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
