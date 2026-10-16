from __future__ import annotations

import gzip
import hashlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from pr87_graupel_diffusion_probe import (  # noqa: E402
    V39_EM_SHA256,
    V39_NATIVE_UPDATE_SHA256,
    V24C_EM_SHA256,
    extend_graupel_diffusion_probe,
    extend_v39_full_source_components,
    extend_v39_graupel_diffusion_probe,
)


FIXTURE = ROOT / "docs/evidence/pr87_two_step_v24c_20261016/module_em_pr85.F.gz"
V39_EM_FIXTURE = ROOT / "docs/evidence/pr87_two_step_v39_20261016/module_em_pr85.F.gz"
V39_NATIVE_FIXTURE = ROOT / "docs/evidence/pr87_two_step_v39_20261016/native_update.f90.gz"


def _source() -> str:
    source = gzip.decompress(FIXTURE.read_bytes()).decode("utf-8")
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == V24C_EM_SHA256
    return source


def _v39_em_source() -> str:
    source = gzip.decompress(V39_EM_FIXTURE.read_bytes()).decode("utf-8")
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == V39_EM_SHA256
    return source


def _v39_native_source() -> str:
    source = gzip.decompress(V39_NATIVE_FIXTURE.read_bytes()).decode("utf-8")
    assert hashlib.sha256(source.encode("utf-8")).hexdigest() == V39_NATIVE_UPDATE_SHA256
    return source


def test_probe_records_mode_qualified_qg_and_qib_without_changing_call():
    source = _source()
    call = "CALL horizontal_diffusion ( 'm', scalar(ims,kms,jms,im),            &"
    result = extend_graupel_diffusion_probe(source)

    assert result.count("'PR87_G_DIFFUSION_PRE'") == 1
    assert result.count("'PR87_G_DIFFUSION_POST'") == 1
    assert result.count("p_qnc, p_qib, tiedtkescheme") == 1
    assert result.count(call) == source.count(call) == 1
    assert result.index("'PR87_G_DIFFUSION_PRE'") < result.index(call)
    assert result.index(call) < result.index("'PR87_G_DIFFUSION_POST'")
    for tag in ("PRE", "POST"):
        tag_index = result.index(f"'PR87_G_DIFFUSION_{tag}'")
        block_start = result.rfind("IF (rk_step == 1", 0, tag_index)
        record = result[block_start:result.index("END IF", tag_index)]
        assert "(moist_step .AND. im == P_QG)" in record
        assert "(.NOT. moist_step .AND. im == P_QIB)" in record
        assert "8, 205, 16" in record
        assert "scalar_tends(8,16,205,im)" in record
        assert "scalar(8,16,205,im)" in record
        assert "scalar(7,16,205,im)" in record
        assert "scalar(9,16,205,im)" in record
        assert "scalar(8,16,204,im)" in record
        assert "scalar(8,16,206,im)" in record


def test_probe_rejects_drifted_preimage():
    source = _source()
    with pytest.raises(ValueError, match="unexpected V24c module_em source"):
        extend_graupel_diffusion_probe(source.replace("scalar_loop : DO im = scs, sce",
                                                      "scalar_loop : DO im = scs + 1, sce"))


def test_v39_probe_records_complete_qg_qib_stencil_at_actual_failure_cell():
    source = _v39_em_source()
    call = "CALL horizontal_diffusion ( 'm', scalar(ims,kms,jms,im),            &"
    result = extend_v39_graupel_diffusion_probe(source)

    assert result.count(call) == source.count(call) == 1
    assert result.count("'PR87_G39_DIFFUSION_PRE'") == 1
    assert result.count("'PR87_G39_DIFFUSION_POST'") == 1
    assert result.count("'PR87_G39_DIFFUSION_RESULT'") == 2
    assert result.index("'PR87_G39_DIFFUSION_PRE'") < result.index(call)
    assert result.index(call) < result.index("'PR87_G39_DIFFUSION_POST'")
    correction = result.index("all_pair_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &")
    exact_result = result.index("'PR87_G39_DIFFUSION_RESULT'")
    deallocation = result.index("DEALLOCATE(pr87_rain_tendency_before,pr87_rain_diffusion_increment)")
    assert correction < exact_result < deallocation

    for phase in ("PRE", "POST"):
        tag_index = result.index(f"'PR87_G39_DIFFUSION_{phase}'")
        block_start = result.rfind("IF (rk_step == 1", 0, tag_index)
        record = result[block_start:result.index("END IF", tag_index)]
        assert "((moist_step .AND. im == P_QG)" in record
        assert "(.NOT. moist_step .AND. im == P_QIB)" in record
        assert "154, 77, 17" in record
        for operand in (
            "scalar(154,17,77,im)", "scalar(153,17,77,im)",
            "scalar(155,17,77,im)", "scalar(154,17,76,im)",
            "scalar(154,17,78,im)", "mut(154,77)", "c1h(17)",
            "xkmhd(154,17,77)", "msfux(154,77)", "msfuy(154,77)",
            "msfvx_inv(154,77)", "msfvy(154,77)", "msftx(154,77)",
            "msfty(154,77)", "rdx, rdy",
        ):
            assert operand in record

    result_block = result[correction:deallocation]
    qg_gate = result_block[result_block.index("IF (rk_step == 1 .AND. moist_step .AND. im == P_QG"):]
    qg_gate = qg_gate[:qg_gate.index("END IF")]
    qib_gate = result_block[result_block.index("IF (rk_step == 1 .AND. .NOT. moist_step .AND. im == P_QIB"):]
    qib_gate = qib_gate[:qib_gate.index("END IF")]
    for gate in (qg_gate, qib_gate):
        assert "pr87_diff_i == 154 .AND. pr87_diff_j == 77 .AND. pr87_diff_k == 17" in gate
    assert "154 >= pr87_diff_i_start .AND. 154 <= pr87_diff_i_end" in result_block
    assert "77 >= pr87_diff_j_start .AND. 77 <= pr87_diff_j_end" in result_block
    for operand in (
        "pr87_rain_tendency_before(154,17,77)",
        "scalar_tends(154,17,77,im)",
        "pr87_rain_diffusion_increment(154,17,77)",
        "all_pair_diffusion_delta(154,17,77,pr87_diff_channel)",
        "REAL(pr87_rain_tendency_before(154,17,77),real64) +",
    ):
        assert operand in result_block


def test_v39_full_source_component_row_is_failure_only_and_p4_scoped():
    source = _v39_native_source()
    result = extend_v39_full_source_components(source)
    full = result.index("WRITE(u,*) 'FULL'")
    component = result.index("'FULL_SOURCE_COMPONENTS'")
    source_failure_branch = result.rfind("IF (.NOT.full_valid) THEN", 0, full)
    branch_end = result.index("END IF", component)
    assert source_failure_branch < full < component < branch_end
    assert "p==4 .AND. PRESENT(pr87_all_pair_diffusion_delta)" in result[source_failure_branch:component]
    block = result[component:branch_end]
    assert "REAL(qs(cell,p),real64),REAL(ns(cell,p),real64)" in block
    assert "pr87_all_pair_diffusion_delta(i,k,j,7),pr87_all_pair_diffusion_delta(i,k,j,8)" in block
    assert "qs64(cell,p),ns64(cell,p),qa64(cell,p),na64(cell,p)" in block
    assert "source_candidate" in block
    assert result.count("'FULL_SOURCE_COMPONENTS'") == 1


def test_v39_transforms_reject_any_unpinned_source():
    with pytest.raises(ValueError, match="unexpected V39 module_em source"):
        extend_v39_graupel_diffusion_probe(_v39_em_source() + "\n")
    with pytest.raises(ValueError, match="unexpected V39 native update fragment"):
        extend_v39_full_source_components(_v39_native_source() + "\n")
