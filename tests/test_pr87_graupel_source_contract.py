from __future__ import annotations

import hashlib
import gzip
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr87_graupel_source_contract import (  # noqa: E402
    V23C_NATIVE_UPDATE_SHA256,
    extend_graupel_strict_mass,
)


V23C_SOURCE = ROOT / "docs/evidence/pr87_two_step_v23c_20261016/native_update.f90.gz"


def _v23c_source() -> str:
    return gzip.decompress(V23C_SOURCE.read_bytes()).decode()


def test_v23c_graupel_strict_mass_transform_and_pin() -> None:
    original = _v23c_source()
    assert hashlib.sha256(original.encode()).hexdigest() == V23C_NATIVE_UPDATE_SHA256
    transformed = extend_graupel_strict_mass(original)

    assert transformed.count(
        "strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.]"
    ) == 1
    assert transformed.count("strict_mass_ratio=(p==4)") == 1
    assert transformed.count("strict_mass_ratio=(pair==4)") == 1
    assert transformed.count("number_pair_bounds=number_bounds, &\n") == 1
    assert transformed.count("strict_mass_ratio=") == 3
    assert ("REAL(rain_pidn,real64)/REAL(rain_lambda_max,real64)**"
            "REAL(rain_power,real64),100.0_real64]") in transformed
    assert ("REAL(rain_pidn,real64)/REAL(rain_lambda_min,real64)**"
            "REAL(rain_power,real64),900.0_real64]") in transformed
    assert "drydensity" in transformed
    assert "number_bounds(cell,1,4)" not in transformed
    assert "source_stored=REAL(source_candidate,real32)\n        IF (p==4) THEN" in transformed
    assert "strict_mass_ratio=.TRUE.)" in transformed
    assert "source_valid=joint_moment_is_valid(source_stored(1),source_stored(2)" in transformed
    assert "IF (p==4) THEN" in transformed
    assert "source_candidate,source_stored,drydensity(cell)" in transformed


def test_source_hash_and_anchor_mutations_are_refused() -> None:
    original = _v23c_source()
    for changed in (
        original.replace("joint_qnb_update", "joint_qnb_updXte", 1),
        original.replace("number_pair_bounds=number_bounds)", "number_pair_bounds=number_bounds, bad=1)", 1),
    ):
        try:
            extend_graupel_strict_mass(changed)
        except ValueError:
            pass
        else:
            raise AssertionError("mutated V23c input was accepted")


if __name__ == "__main__":
    test_v23c_graupel_strict_mass_transform_and_pin()
    test_source_hash_and_anchor_mutations_are_refused()
    print("PR87 graupel source-contract tests PASS")
