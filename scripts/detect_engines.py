#!/usr/bin/env python3
"""Print the chord-engine compatibility status as JSON."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.engine_support import detect_engines


if __name__ == "__main__":
    print(json.dumps(detect_engines(), ensure_ascii=False, indent=2))
