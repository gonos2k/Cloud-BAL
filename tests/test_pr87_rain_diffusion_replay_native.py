from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from pr87_rain_diffusion_replay import require_helper_source


def test_helper_source_procedure_is_hash_pinned() -> None:
    receipt = require_helper_source()
    assert receipt["routine_sha256"] == "cbcc347345a6449b9e5666407c5ef8c6a0db73a9a397d0e306ad14a085783ac3"
