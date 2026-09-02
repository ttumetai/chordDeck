import hashlib
import io
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException, UploadFile

import backend.main as main
from backend.chords import collapse_duplicates, postprocess, simplify_chord
from backend.main import _save_and_hash, _validate_engine


class ChordLogicTests(unittest.TestCase):
    def test_simplify_common_extensions_and_inversions(self):
        self.assertEqual(simplify_chord("Bb6"), "Bb")
        self.assertEqual(simplify_chord("D/F#"), "D")
        self.assertEqual(simplify_chord("Am7b5/G"), "Am7")
        self.assertEqual(simplify_chord("Cmaj7"), "Cmaj7")
        self.assertEqual(simplify_chord("N"), "N")

    def test_postprocess_merges_short_segments_and_collapses_duplicates(self):
        full, simple = postprocess([
            {"timestamp": 0.0, "chord": "N"},
            {"timestamp": 0.2, "chord": "C"},
            {"timestamp": 1.0, "chord": "C"},
            {"timestamp": 2.0, "chord": "Bb6"},
        ])
        self.assertEqual(full, [
            {"timestamp": 0.0, "chord": "N"},
            {"timestamp": 1.0, "chord": "C"},
            {"timestamp": 2.0, "chord": "Bb6"},
        ])
        self.assertEqual(simple[-1], {"timestamp": 2.0, "chord": "Bb"})

    def test_collapse_duplicates_preserves_first_timestamp(self):
        self.assertEqual(
            collapse_duplicates([
                {"timestamp": 0, "chord": "C"},
                {"timestamp": 1, "chord": "C"},
                {"timestamp": 2, "chord": "G"},
            ]),
            [{"timestamp": 0, "chord": "C"}, {"timestamp": 2, "chord": "G"}],
        )

    def test_engine_validation(self):
        self.assertEqual(_validate_engine(" ChOrDiNo "), "chordino")
        with self.assertRaises(HTTPException) as ctx:
            _validate_engine("unknown")
        self.assertEqual(ctx.exception.status_code, 422)


class UploadLimitTests(unittest.TestCase):
    def test_analyze_endpoint_rejects_oversize_upload(self):
        original = main.MAX_UPLOAD_BYTES
        main.MAX_UPLOAD_BYTES = 4
        try:
            with self.assertRaises(HTTPException) as ctx:
                main.analyze(
                    UploadFile(file=io.BytesIO(b"12345"), filename="audio.wav"), "auto"
                )
            self.assertEqual(ctx.exception.status_code, 413)
        finally:
            main.MAX_UPLOAD_BYTES = original

    def test_save_and_hash_returns_md5_and_size(self):
        payload = b"chord-deck"
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "audio.wav"
            md5, size = _save_and_hash(io.BytesIO(payload), dest, max_bytes=100)
        self.assertEqual(size, len(payload))
        self.assertEqual(md5, hashlib.md5(payload).hexdigest())

    def test_save_and_hash_rejects_payload_over_limit(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "audio.wav"
            with self.assertRaisesRegex(ValueError, "超过"):
                _save_and_hash(io.BytesIO(b"12345"), dest, max_bytes=4)
            self.assertEqual(dest.read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
