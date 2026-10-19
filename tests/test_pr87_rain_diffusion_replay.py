from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_rain_diffusion_replay import (  # noqa: E402
    _VALUE_NAMES,
    _bits32,
    _pair_records,
    RAIN_BOUNDS,
    _stencil32,
    _stencil64,
    require_helper_source,
)


VALUES = {
    "dt_step": 0.5,
    "khdq": 0.0,
    "tendency": 1.0,
    "field_center": 1.0,
    "field_xminus": 0.0,
    "field_xplus": 2.0,
    "field_yminus": 0.0,
    "field_yplus": 2.0,
    "mut_center": 1.0,
    "mut_xminus": 0.0,
    "mut_xplus": 1.0,
    "mut_yminus": 0.0,
    "mut_yplus": 1.0,
    "c1": 1.0,
    "c2": 0.0,
    "xkmhd_center": 1.0,
    "xkmhd_xminus": 1.0,
    "xkmhd_xplus": 1.0,
    "xkmhd_yminus": 1.0,
    "xkmhd_yplus": 1.0,
    "msfux_xminus": 1.0,
    "msfux_center": 1.0,
    "msfux_xplus": 1.0,
    "msfuy_xminus": 1.0,
    "msfuy_center": 1.0,
    "msfuy_xplus": 1.0,
    "msfvx_inv_center": 1.0,
    "msfvx_inv_yplus": 1.0,
    "msfvy_center": 1.0,
    "msfvy_yplus": 1.0,
    "msftx": 1.0,
    "msfty": 1.0,
    "rdx": 1.0,
    "rdy": 1.0,
}


def _record(tag: str, index: int, moist: bool, tendency: float) -> str:
    values = dict(VALUES, tendency=tendency)
    numbers = " ".join(f"{values[name]:.17E}" for name in _VALUE_NAMES)
    return f"{tag} 1 {index} 110 5 18 {'T' if moist else 'F'} F {numbers}"


def test_exact_dyadic_stencil_matches_native_rounding_and_r64() -> None:
    assert _stencil32(VALUES) == 1.0
    assert _stencil64(VALUES) == 1.0


def test_tags_pair_qr_and_qnr_by_moist_flag_and_registry_index() -> None:
    lines = [
        _record("PR87_RAIN_DIFFUSION_PRE", 6, True, 1.0),
        _record("PR87_RAIN_DIFFUSION_POST", 6, True, 2.0),
        _record("PR87_RAIN_DIFFUSION_PRE", 4, True, 1.0),
        _record("PR87_RAIN_DIFFUSION_POST", 4, True, 2.0),
        _record("PR87_RAIN_DIFFUSION_PRE", 4, False, 1.0),
        _record("PR87_RAIN_DIFFUSION_POST", 4, False, 2.0),
        _record("PR87_RAIN_DIFFUSION_PRE", 6, False, 1.0),
        _record("PR87_RAIN_DIFFUSION_POST", 6, False, 2.0),
    ]
    import pr87_rain_diffusion_replay as replay_module

    records = replay_module._read_probe_records_from_text("\n".join(lines))
    pairs = _pair_records(records)
    assert [(pair["species"], pair["registry_index"]) for pair in pairs] == [
        ("QR", 4), ("QNR", 6)
    ]
    assert all(pair["native_post_bit_match"] for pair in pairs)
    assert all(_bits32(pair["r64_delta"]) == _bits32(1.0) for pair in pairs)


def test_helper_source_procedure_is_hash_pinned() -> None:
    receipt = require_helper_source()
    assert receipt["routine_sha256"] == "cbcc347345a6449b9e5666407c5ef8c6a0db73a9a397d0e306ad14a085783ac3"


def test_bounds_match_native_rain_lambda_contract() -> None:
    assert RAIN_BOUNDS == (
        12566.37109375 / 35000.0**3,
        12566.37109375 / 961.0**3,
    )
