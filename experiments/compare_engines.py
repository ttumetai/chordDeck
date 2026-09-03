#!/usr/bin/env python3
"""Compare lv-chordia devices and, optionally, the existing local engines."""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "experiments" / "lv_chordia_adapter.py"
sys.path.insert(0, str(ROOT))


def _write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def run_lv(audio: Path, lv_python: Path, device: str, vocabulary: str) -> dict:
    result = subprocess.run(
        [str(lv_python), str(ADAPTER), str(audio), "--device", device, "--vocabulary", vocabulary],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"exit {result.returncode}")
    return json.loads(result.stdout)


def run_current(audio: Path, engine: str) -> dict:
    from backend import chords

    started = time.perf_counter()
    if engine == "librosa-template":
        raw = chords._extract_librosa(str(audio))
        source = "chroma-template"
    else:
        raw, source = chords.extract_chords(str(audio), engine)
    elapsed = time.perf_counter() - started
    duration = chords.get_duration(str(audio)) or 0.0
    normalized = [{"timestamp": item["timestamp"], "chord": item["chord"]} for item in raw]
    return {
        "engine": engine,
        "source": source,
        "duration": duration,
        "elapsed_seconds": round(elapsed, 3),
        "realtime_factor": round(elapsed / duration, 4) if duration else None,
        "peak_memory_mb": None,
        "chord_count": len(normalized),
        "unique_chords": sorted({item["chord"] for item in normalized}),
        "chords": normalized,
    }


def summary(audio: Path, payloads: list[tuple[str, dict]]) -> str:
    lines = [f"# Engine comparison: `{audio.name}`", "", "| Engine | Device | Elapsed (s) | RTF | Peak RSS (MB) | Chords |", "|---|---:|---:|---:|---:|---:|"]
    for name, payload in payloads:
        lines.append(
            f"| {name} | {payload.get('device', '')} | {payload.get('elapsed_seconds', '')} | "
            f"{payload.get('realtime_factor', '')} | {payload.get('peak_memory_mb', '')} | {payload.get('chord_count', '')} |"
        )
    lines += ["", "## Recognition", ""]
    for name, payload in payloads:
        lines.append(f"### {name}")
        lines.append("")
        if "error" in payload:
            lines.append(f"Error: `{payload['error']}`")
            lines.append("")
            continue
        lines.append("`" + " -> ".join(item.get("chord", "") for item in payload["chords"]) + "`")
        lines.append("")
    cpu = next((payload for name, payload in payloads if name == "lv-chordia-cpu"), {})
    mps = next((payload for name, payload in payloads if name == "lv-chordia-mps"), {})
    lines += ["## Compatibility", ""]
    if cpu.get("error") or mps.get("error"):
        lines.append(f"CPU: {'failed' if cpu.get('error') else 'passed'}; MPS: {'failed' if mps.get('error') else 'passed'}.")
    else:
        speed = mps["elapsed_seconds"] / cpu["elapsed_seconds"]
        same = [item.get("chord") for item in cpu["chords"]] == [item.get("chord") for item in mps["chords"]]
        speed_result = "met" if speed <= 0.8 else "was not met"
        lines.append("Apple Silicon ARM64: passed. CPU and MPS completed without device errors.")
        lines.append(
            f"CPU: {cpu['elapsed_seconds']}s, {cpu['peak_memory_mb']}MB peak RSS; "
            f"MPS: {mps['elapsed_seconds']}s, {mps['peak_memory_mb']}MB peak RSS."
        )
        lines.append(f"MPS speed ratio vs CPU: {speed:.3f}x; outputs identical: {'yes' if same else 'no'}. The 20% speedup threshold {speed_result}.")
        current = [
            f"{name}={payload.get('chord_count')} segments"
            for name, payload in payloads
            if not name.startswith("lv-chordia") and "error" not in payload
        ]
        if current:
            lines.append("Current baseline segment counts: " + ", ".join(current) + ".")
        lines.append("No accuracy winner is inferred without ground-truth labels; keep lv-chordia out of the default engine pending a larger labeled evaluation.")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--lv-python", type=Path, default=ROOT / ".venv-lv" / "bin" / "python")
    parser.add_argument("--vocabulary", choices=("submission", "ismir2017", "full"), default="submission")
    parser.add_argument("--include-current", action="store_true")
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error(f"audio file not found: {args.audio}")

    output_dir = ROOT / "experiments" / "results" / args.audio.stem
    output_dir.mkdir(parents=True, exist_ok=True)
    payloads: list[tuple[str, dict]] = []
    for device in ("cpu", "mps"):
        name = f"lv-chordia-{device}"
        try:
            payload = run_lv(args.audio.resolve(), args.lv_python, device, args.vocabulary)
        except Exception as exc:  # noqa: BLE001
            payload = {"engine": "lv-chordia", "device": device, "error": str(exc)}
        _write(output_dir / f"lv-chordia-{device}.json", payload)
        payloads.append((name, payload))

    if args.include_current:
        for engine in ("deepchroma", "chordino", "librosa-template"):
            try:
                payload = run_current(args.audio.resolve(), engine)
            except Exception as exc:  # noqa: BLE001
                payload = {"engine": engine, "error": str(exc)}
            _write(output_dir / f"{engine}.json", payload)
            payloads.append((engine, payload))

    (output_dir / "summary.md").write_text(summary(args.audio, payloads))
    print(output_dir / "summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
