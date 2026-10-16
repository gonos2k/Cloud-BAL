from __future__ import annotations

import gzip
import hashlib
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from pr87_all_pair_diffusion_precision import (  # noqa: E402
    HELPER_SHA256,
    PINNED_SHA256,
    extend_all_pair_diffusion_precision,
)
from pr87_rain_diffusion_precision import _call_span  # noqa: E402


FIXTURE = ROOT / "tests/fixtures/pr87_all_pair_diffusion_v26base"
HELPER = ROOT / "tools/pr87_horizontal_diffusion64.f90"


def _read(name: str) -> str:
    return gzip.decompress((FIXTURE / f"{name}.gz").read_bytes()).decode()


@pytest.fixture(scope="module")
def sources() -> dict[str, str]:
    return {
        "em": _read("module_em_pr85.F"),
        "solve": _read("solve_em.F"),
        "fragment": _read("native_update.f90"),
        "helper": HELPER.read_text(),
    }


@pytest.fixture(scope="module")
def generated(sources: dict[str, str]) -> dict[str, str]:
    return extend_all_pair_diffusion_precision(sources)


def test_inputs_are_exact_pbl_payload_and_four_channel_preimage(sources: dict[str, str]) -> None:
    hashes = {name: hashlib.sha256(sources[name].encode()).hexdigest()
              for name in PINNED_SHA256}
    assert hashes == PINNED_SHA256
    assert hashlib.sha256(sources["helper"].encode()).hexdigest() == HELPER_SHA256
    assert "pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)" in sources["fragment"]


def test_selector_binds_all_four_pairs_to_registry_mode_and_preserves_host_call(
    sources: dict[str, str], generated: dict[str, str]
) -> None:
    em = generated["em"]
    old_routine = sources["em"].split("SUBROUTINE rk_scalar_tend", 1)[1].split(
        "END SUBROUTINE rk_scalar_tend", 1)[0]
    new_routine = em.split("SUBROUTINE rk_scalar_tend", 1)[1].split(
        "END SUBROUTINE rk_scalar_tend", 1)[0]
    import_lines = [line.lower() for line in em.splitlines()
                    if "use module_state_description, only:" in line.lower()]
    assert len(import_lines) == 1
    assert import_lines[0].count("p_qni") == 1
    assert import_lines[0].count("p_qib") == 1
    _, _, old_call = _call_span(old_routine, "horizontal_diffusion")
    assert new_routine.count("CALL horizontal_diffusion (") == 1
    assert old_call in new_routine
    assert "PRESENT(all_pair_diffusion_delta) .AND. rk_step == 1" in new_routine
    for mode, registry, channel in (
        ("moist_step", "P_QC", 1), (".NOT. moist_step", "P_QNC", 2),
        ("moist_step", "P_QI", 3), (".NOT. moist_step", "P_QNI", 4),
        ("moist_step", "P_QR", 5), (".NOT. moist_step", "P_QNR", 6),
        ("moist_step", "P_QG", 7), (".NOT. moist_step", "P_QIB", 8),
    ):
        assert f"{mode} .AND. im == {registry}" in new_routine
        assert f"pr87_diff_channel = {channel}" in new_routine
    assert "all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)" in new_routine
    assert new_routine.count("CALL horizontal_diffusion64(") == 1

    solve = generated["solve"]
    assert "pr87_all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)" in solve
    assert "pr87_all_pair_diffusion_delta = 0.0_real64" in solve
    calls = []
    for match in re.finditer(r"\bCALL\s+rk_scalar_tend\b", solve):
        _, _, call = _call_span(solve, "rk_scalar_tend", match.start())
        calls.append(call)
    assert len(calls) >= 2
    assert sum("all_pair_diffusion_delta=pr87_all_pair_diffusion_delta" in call
               for call in calls) == 2


def test_native_maps_each_pair_and_restores_source_first_without_double_add(
    generated: dict[str, str]
) -> None:
    fragment = generated["fragment"]
    assert "all_pair_diffusion_delta(ims:ime,kms:kme,jms:jme,8)" in fragment
    assert "diffusion_delta_sum(8),diffusion_delta_l1(8),diffusion_delta_max(8)" in fragment
    assert "IF (p>=1.AND.p<=4.AND.PRESENT(pr87_all_pair_diffusion_delta)) THEN" in fragment
    assert "pr87_all_pair_diffusion_delta(i,k,j,2*p-1)" in fragment
    assert "pr87_all_pair_diffusion_delta(i,k,j,2*p)" in fragment
    later = fragment.index("qs64(cell,p)=pr87_later_qsrc(i,k,j,p)")
    restore = fragment.index("IF (p>=1.AND.p<=2.AND.PRESENT(pr87_all_pair_diffusion_delta))", later)
    check = fragment.index("source_sum64=(REAL(oldcarrier(cell),real64)", restore)
    assert later < restore < check
    assert "ALL_PAIR_DIFFUSION_RK_CORRECTION" in fragment
    assert "pr87_all_pair_diffusion_precision.raw" in fragment
    assert "pr87_pbl_tendency_delta64(ims:ime,kms:kme,jms:jme,4)" in fragment


def test_bad_source_pin_is_rejected_before_transform(sources: dict[str, str]) -> None:
    with pytest.raises(ValueError, match="em source SHA-256 mismatch"):
        extend_all_pair_diffusion_precision({**sources, "em": sources["em"] + "! drift\n"})
