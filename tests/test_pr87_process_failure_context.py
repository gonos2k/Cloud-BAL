from __future__ import annotations

import gzip
import hashlib
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs/evidence/pr87_two_step_v34_20261016/module_mp_kdm6.F.gz"
sys.path.insert(0, str(ROOT / "tools"))

from pr87_process_failure_context import (  # noqa: E402
    V34_KDM6_SHA256,
    V36_KDM6_SHA256,
    V38_KDM6_SHA256,
    V39_KDM6_SHA256,
    V39_FINAL_KDM6_SHA256,
    add_process_failure_context,
    add_ice_sedimentation_context,
    add_ice_process_endpoint_context,
)


@pytest.mark.parametrize("version", ["V34", "V36", "V38", "V39"])
def test_failure_context_is_hash_pinned_and_diagnostic_only(version):
    if version == "V34":
        source = gzip.open(SOURCE, "rt").read()
        expected = V34_KDM6_SHA256
    elif version in ("V36", "V38"):
        archive = ROOT / f"docs/evidence/pr87_two_step_{version.lower()}_20261016/module_mp_kdm6.F.gz"
        source = gzip.open(archive, "rt").read()
        start = source.index("              write(*,'(a,9(1x,i0))') 'PR87_GSEARCH_FAIL_META'")
        end = source.index("              if (.not.rain_bg_rates_feasible) then", start)
        source = source[:start] + source[end:]
        expected = V36_KDM6_SHA256 if version == "V36" else V38_KDM6_SHA256
    else:
        from pr87_graupel_process_domain import extend_graupel_process_domain
        parent = ROOT / "docs/evidence/pr87_two_step_v31_20261016/module_mp_kdm6.F.gz"
        source = extend_graupel_process_domain(gzip.open(parent, "rt").read())
        expected = V39_KDM6_SHA256
    assert hashlib.sha256(source.encode()).hexdigest() == expected

    transformed = add_process_failure_context(source)
    marker = transformed.index("              write(*,'(a,9(1x,i0))') 'PR87_GSEARCH_FAIL_META'")
    end = transformed.index("              if (.not.rain_bg_rates_feasible) then", marker)
    diagnostic = transformed[marker:end]
    assert transformed.count("PR87_GSEARCH_FAIL_META") == 1
    assert transformed.count("PR87_GSEARCH_FAIL_STATE") == 1
    assert transformed.count("PR87_GSEARCH_FAIL_CONFIG") == 1
    assert transformed.rfind("if (.not.rain_process_feasible) then", 0, marker) >= 0
    assert "error stop 'KDM6 cold rain process rejected an infeasible moment state'" in transformed[end:]
    for operand in (
        "rain_g_q_process", "rain_g_n_process", "rain_g_bg_process", "rain_g_t_process",
        "rain_g_qv_process", "rain_g_alpha", "rain_process_search_status",
        "dry_carrier_density(i,k)", "ice_full_sublimation_pending(i,k)",
        "real(PR85_ICE_NATIVE_INACTIVE_MAX,8)",
    ):
        assert operand in diagnostic
    assert "rain_q_fixed,8),real(rain_g_q_process,8)" in diagnostic
    assert "rain_n_fixed,8),real(rain_g_n_process,8)" in diagnostic

    # Removing the inserted reporter recovers the source byte-for-byte.
    recovered = transformed[:marker] + transformed[end:]
    assert recovered == source
    with pytest.raises(ValueError, match="unexpected KDM6 source hash"):
        add_process_failure_context(source + "\n")


def test_ice_sedimentation_context_is_v39_pinned_and_failure_only():
    archive = ROOT / "docs/evidence/pr87_two_step_v39_20261016/module_mp_kdm6.F.gz"
    source = gzip.open(archive, "rt").read()
    assert hashlib.sha256(source.encode()).hexdigest() == V39_FINAL_KDM6_SHA256

    transformed = add_ice_sedimentation_context(source)
    assert transformed.count("PR87_ICE_SED_OUTLIER") == 1
    assert transformed.count("PR87_ICE_SED_STATE") == 1
    assert transformed.count("PR87_ICE_SED_COLUMN") == 1
    assert transformed.count("PR87_ICE_SED_REPLAY") == 1

    original_call = """            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep_i(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,4), &
                 number_velocity_rate(i,kts:kte,2),qci(i,kts:kte,2),nci(i,kts:kte,2), &
                 PR85_SED_ICE,0.0,0.0,0.0,0.0,pr85_ice_qrate,pr85_ice_nrate, &
                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid,0.0,0.0,0.0,0.0)
            if (.not.pr85_ice_valid) error stop 'PR85 ice sedimentation packet rejected'
"""
    call_start = transformed.index("            pr87_ice_q_before=qci(i,kts:kte,2)")
    call_end = transformed.index("            do k = kts, kte\n              falk(i,k,4)", call_start)
    inserted = transformed[call_start:call_end]
    assert original_call in inserted
    assert "if (pr87_model_timestep.eq.2) then" in inserted
    assert "dend(i,k)" in inserted and "delz(i,k)" in inserted
    assert "mass_velocity_rate(i,k,4)" in inserted
    assert "number_velocity_rate(i,k,2)" in inserted
    assert "real(qmin,8)" in inserted
    assert "pr87_model_timestep,lat,i,k,loop,n,mstep_i(i)" in inserted
    assert "SPACING(REAL(pr87_ice_diag_lower))" in inserted
    assert "pr87_ice_diag_ratio.ge.pr87_ice_diag_lower-pr87_ice_diag_lower_tol" in inserted
    assert "transfer(pr87_ice_q_before(k),0)" in inserted

    declaration_block = """   real :: pr87_ice_q_before(kts:kte),pr87_ice_n_before(kts:kte)
   real(kind=8) :: pr87_ice_diag_ratio,pr87_ice_diag_lower,pr87_ice_diag_upper
   real(kind=8) :: pr87_ice_diag_lower_tol,pr87_ice_diag_upper_tol
   integer :: pr87_ice_diag_bits(4),pr87_ice_diag_first
   logical :: pr87_ice_diag_column_written
"""
    recovered = transformed[:call_start] + original_call + transformed[call_end:]
    recovered = recovered.replace(declaration_block, "", 1)
    assert recovered == source
    with pytest.raises(ValueError, match="unexpected V39 KDM6 source hash"):
        add_ice_sedimentation_context(source + "\n")
    with pytest.raises(ValueError, match="unexpected V39 KDM6 source hash"):
        add_ice_sedimentation_context(transformed)


def test_ice_process_endpoint_context_only_enables_scoped_existing_rows():
    archive = ROOT / "docs/evidence/pr87_two_step_v39_20261016/module_mp_kdm6.F.gz"
    source = gzip.open(archive, "rt").read()
    assert hashlib.sha256(source.encode()).hexdigest() == V39_FINAL_KDM6_SHA256

    transformed = add_ice_process_endpoint_context(source)
    assert transformed.count("PR87_KDM6_COLD_T2") == 1
    assert transformed.count("PR87_KDM6_WARM_T2") == 1
    assert "if (.false.) then" not in transformed
    assert transformed.count("pr87_ice_process_diag=.false.") == 2

    cold_start = transformed.index("            pr87_ice_process_diag=.false.")
    cold_end = transformed.index("            write(pr85_cold_unit", cold_start)
    cold = transformed[cold_start:cold_end]
    assert "pr87_model_timestep.eq.2" in cold
    assert "qci(i,k,2).le.1.0e-14" in cold
    assert "nci(i,k,2).gt.0.0" in cold
    assert "dry_carrier_density(i,k).gt.0.0" in cold
    assert "SPACING(REAL(pr87_ice_process_lower))" in cold
    assert "DBLE(dry_carrier_density(i,k))*" in cold
    assert "PR87_KDM6_COLD_T2',pr87_model_timestep,i,lat,k,loop" in transformed
    assert "qci(i,k,2)=" not in cold and "nci(i,k,2)=" not in cold

    warm_start = transformed.index("            ! Existing full v17 ledgers remain the reference.")
    warm_end = transformed.index("            write(pr85_warm_unit", warm_start)
    warm = transformed[warm_start:warm_end]
    assert "pr87_model_timestep.eq.2" in warm
    assert "rain_warm_q_after(2).le.1.0e-14" in warm
    assert "rain_warm_n_after(2).gt.0.0" in warm
    assert "pr87_ice_warm_label='PR87_KDM6_WARM_T2'" in warm
    assert "rain_warm_search_status.eq.1 .or. pr87_ice_process_diag" in warm
    assert "'(a,7i8,1x,2l1" in transformed
    assert "'(a,8i8,1x,2l1" not in transformed

    with pytest.raises(ValueError, match="unexpected V39 KDM6 source hash"):
        add_ice_process_endpoint_context(source + "\n")
    with pytest.raises(ValueError, match="unexpected V39 KDM6 source hash"):
        add_ice_process_endpoint_context(transformed)
