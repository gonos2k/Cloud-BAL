from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from pr87_admission_reason_overlay import add_admission_reasons  # noqa: E402


SOURCE = Path(
    "/var/tmp/pr85_native_joint_candidate_20261015v17/source/phys/module_mp_kdm6.F"
)
SOURCE_SHA256 = "b5e61526dc1e3d3384b9c87a423affc1cc2182faa18a904468114ec52b6781b8"


@pytest.fixture(scope="module")
def transformed_source() -> str:
    if not SOURCE.is_file():
        pytest.skip(f"pinned PR85 source is not available: {SOURCE}")
    original = SOURCE.read_text()
    assert hashlib.sha256(original.encode()).hexdigest() == SOURCE_SHA256
    return add_admission_reasons(original)


def test_validator_optional_reason_tags_exact_checks(transformed_source: str) -> None:
    validator = transformed_source.split(
        "subroutine kdm6_rain_process_state_valid(", 1
    )[1].split("end subroutine kdm6_rain_process_state_valid", 1)[0]
    assert "integer, intent(out), optional :: failure_reason" in validator
    assert "if (present(failure_reason)) failure_reason=5" in validator
    assert "if (present(failure_reason)) failure_reason=6" in validator
    assert "if (present(failure_reason)) failure_reason=7" in validator
    assert "if (present(failure_reason)) failure_reason=9" in validator
    # These are the original source arithmetic expressions, still evaluated
    # once in their original order; the overlay only surrounds their returns.
    assert validator.count(
        "real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)"
    ) == 1
    assert validator.count(
        "real(bg,8).lt.real(q(5),8)/real(rho_max,8)"
    ) == 1
    assert "if (q(4).lt.0.0 .or. q(5).lt.0.0) then" in validator
    assert "if (present(failure_reason)) failure_reason=2" in validator
    assert ") return" not in validator


def test_aut_and_g_probe_full_proposal_before_fraction_call(
    transformed_source: str,
) -> None:
    assert transformed_source.count("failure_reason=pr87_aut_reason") == 1
    assert transformed_source.count("failure_reason=pr87_g_reason") == 1
    assert "rain_q_fixed+rain_aut_q_process" in transformed_source
    assert "rain_n_fixed+rain_aut_n_process" in transformed_source
    assert "rain_q_fixed+rain_g_q_process" in transformed_source
    assert "rain_n_fixed+rain_g_n_process" in transformed_source
    assert "rain_bg_fixed+rain_g_bg_process" in transformed_source
    assert "rain_t_fixed+rain_g_t_process" in transformed_source
    assert "rain_qv_stage+rain_g_qv_process" in transformed_source
    assert "merge(1,0,rain_full_evap_pending(i,k))" in transformed_source
    assert transformed_source.count("'# PR87_ADMISSION") == 1
    assert "file='pr87_admission_reason.raw'" in transformed_source
    assert "status='unknown',position='append'" in transformed_source
    assert "status='replace'" not in transformed_source.split(
        "pr87_admission_reason.raw", 1
    )[0][-400:]
    assert transformed_source.count("'PR87_ADMISSION','AUT'") == 1
    assert transformed_source.count("'PR87_ADMISSION','G'") == 1
    assert "rain_aut_alpha.lt.1.0" in transformed_source
    assert "rain_g_alpha.lt.1.0" in transformed_source
    assert "pr87_mass_specific=0.5*sum(abs(rain_aut_q_process))" in transformed_source
    assert "0.5*(sum(abs(rain_g_q_process))+abs(rain_g_qv_process))" in transformed_source
    assert "rhoDry_kg_m3,DELZ_m" in transformed_source


def test_transform_rejects_second_application(transformed_source: str) -> None:
    with pytest.raises(ValueError):
        add_admission_reasons(transformed_source)


def test_transform_preserves_validator_predicates_in_order(
    transformed_source: str,
) -> None:
    original = SOURCE.read_text()

    def conditions(source: str) -> list[str]:
        body = source.split("subroutine kdm6_rain_process_state_valid(", 1)[1]
        body = body.split("end subroutine kdm6_rain_process_state_valid", 1)[0]
        result = []
        position = 0
        while match := re.search(r"\bif\s*\(", body[position:], flags=re.IGNORECASE):
            expression_start = position + match.end()
            depth = 1
            cursor = expression_start
            while depth and cursor < len(body):
                depth += (body[cursor] == "(") - (body[cursor] == ")")
                cursor += 1
            assert depth == 0
            expression = " ".join(body[expression_start:cursor - 1].split())
            result.append(expression)
            position = cursor
        return [item for item in result if item != "present(failure_reason)"]

    assert conditions(transformed_source) == conditions(original)

