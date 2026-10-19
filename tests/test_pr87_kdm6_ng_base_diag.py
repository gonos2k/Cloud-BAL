from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pr87_kdm6_ng_base_diag as diag  # noqa: E402


def test_supports_both_frozen_module_identities() -> None:
    assert diag.V11A_MODULE_SOURCE_SHA256 in diag.SUPPORTED_MODULE_SOURCE_SHA256
    assert diag.V13_MODULE_SOURCE_SHA256 in diag.SUPPORTED_MODULE_SOURCE_SHA256


FATAL = (
    "                if (.not.rain_ng_base_valid .or. rain_qv_before.lt.0.0 .or. &\n"
    "                    .not.ieee_is_finite(rain_qv_before)) &\n"
    "                  error stop 'KDM6 invalid base before nongraupel admission'\n"
)
FIXTURE = "subroutine kdm62D\n" + FATAL + "end subroutine kdm62D\n"


def test_inserts_readonly_values_before_same_fatal_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    fixture_sha = hashlib.sha256(FIXTURE.encode()).hexdigest()
    monkeypatch.setattr(diag, "SUPPORTED_MODULE_SOURCE_SHA256", frozenset({fixture_sha}))

    output = diag.generate_ng_base_diagnostic(FIXTURE)

    assert output.count("error stop 'KDM6 invalid base before nongraupel admission'") == 1
    assert output.index("PR87_NG_BASE_FAIL_META") < output.index("error stop")
    assert "pr87_model_timestep,lat,i,k,loop,n" in output
    for record in (
        "PR87_NG_BASE_FAIL_STATE",
        "PR87_NG_BASE_FAIL_STATE_HEX",
        "PR87_NG_BASE_FAIL_QPROC",
        "PR87_NG_BASE_FAIL_NPROC",
        "PR87_NG_BASE_FAIL_BGTVPROC",
        "PR87_NG_BASE_FAIL_LIMITS",
    ):
        assert record in output
    assert "rain_ng_search_status,rain_full_evap_pending(i,k),rain_ng_base_valid" in output
    assert "rain_q_fixed,rain_n_fixed" in output
    assert "(a,12(1x,z8.8))" in output
    assert "transfer([rain_q_fixed,rain_n_fixed,rain_bg_fixed,rain_t_fixed" in output
    assert output.index("flush(6)") < output.index("error stop")


def test_rejects_source_or_fatal_guard_drift(monkeypatch: pytest.MonkeyPatch) -> None:
    changed_guard = FIXTURE.replace("error stop", "stop")
    monkeypatch.setattr(
        diag,
        "SUPPORTED_MODULE_SOURCE_SHA256",
        frozenset({hashlib.sha256(changed_guard.encode()).hexdigest()}),
    )
    with pytest.raises(ValueError, match="nongraupel base rejection guard"):
        diag.generate_ng_base_diagnostic(changed_guard)
    monkeypatch.setattr(diag, "SUPPORTED_MODULE_SOURCE_SHA256", frozenset({hashlib.sha256(FIXTURE.encode()).hexdigest()}))
    with pytest.raises(ValueError, match="source identity mismatch"):
        diag.generate_ng_base_diagnostic(FIXTURE + "! changed\n")
