from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import pr92_source_store_fixture as fixture


def test_generated_harness_compiles_and_calls_both_store_cores() -> None:
    producer = {
        "step": 1, "rk": 1, "channel": 7, "im": 1, "i": 0, "j": 0, "k": 1,
        "stencil": {dy: ["00000000"] * 9 for dy in (-1, 0, 1)},
        "metrics32_bits": ["3F800000"] * 10,
        "scale32_bits": ["00000000", "3F800000", "3F800000", "3F800000"],
        "before32_bits": "00000000", "after32_bits": "00000000",
        "diffusion64_bits": "0000000000000000",
    }
    store = {
        "context": "FULL", "step": 1, "rk": 1, "i": 0, "j": 0, "k": 1,
        "cell": 1, "failure_stage": 0,
        "candidate_bits64": [
            struct.pack(">d", value).hex().upper()
            for value in (100.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 100.0, 900.0, 1.0, 1.0, 100.0, 1.0)
        ],
        "r32_bits": [
            struct.pack(">f", value).hex().upper()
            for value in (1.0, 1.0, 1.0, 1.0, 100.0, 1.0)
        ],
    }
    identity = {
        "step": 1, "rk": 1, "i": 0, "j": 0, "k": 1, "cell": 1,
        "producer_identity": [1, 1, 7, 1, 0, 0, 1],
        "r64_bits": ["0000000000000000"] * 12, "r64": [0.0] * 12,
        "r32_bits": ["00000000"] * 8,
        "stencil": {dy: ["00000000"] * 12 for dy in (-1, 0, 1)},
        "metrics32_bits": ["3F800000"] * 10,
        "face_coeff64_bits": ["0000000000000000"] * 16,
        "cache_delta64_bits": ["0000000000000000"] * 2,
    }
    data = fixture._data_module({(1, 1, 7, 1, 0, 0, 1): producer}, [store], [identity])
    sources = fixture._core_sources(fixture.POLICY_CORE.read_text())
    sources["d1_helpers.f90"] = fixture._adapter(fixture.D1_SOURCE.read_text())
    sources["captures.f90"] = data
    sources["fixture.f90"] = fixture._harness()

    compiled = fixture.store_replay.run_source_profile("O0", sources, executable="fixture_test")

    assert "PRODUCER_REPLAY" in compiled["stdout"]
    assert "IDENTITY_REPLAY" in compiled["stdout"]
    assert "STORE_REPLAY" in compiled["stdout"]
