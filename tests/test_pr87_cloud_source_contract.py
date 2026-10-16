"""Selected native producer coefficients must match the consuming source."""
import gzip
import hashlib
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = runpy.run_path(str(ROOT / "tools/pr87_cloud_source_contract.py"))
ARCHIVE = ROOT / "docs/evidence/pr87_two_step_v22b_20261016"


def test_native_cloud_and_rain_share_source_defined_contract():
    original = gzip.decompress((ARCHIVE / "native_update.f90.gz").read_bytes()).decode()
    assert hashlib.sha256(original.encode()).hexdigest() == TRANSFORM["FRAGMENT_SHA256"]
    result = TRANSFORM["extend_cloud_source_contract"](original)
    assert "cloud_pidn=523.59881591796875_real32" in result
    assert "4.188790204786391e-15" not in result
    assert "3.0300855069345996e-10" not in result
    assert "number_bounds(cells,2,4)" in result
    assert "number_bounds=0.0_real64" in result
    assert "number_bounds(cell,1,1)=REAL(drydensity(cell),real64)*" in result
    assert "REAL(cloud_lambda_min,real64)**REAL(cloud_power,real64)/REAL(cloud_pidn,real64)" in result
    assert "number_pair_bounds=number_bounds" in result
    assert "strict_number_pair=3" not in result
    assert "volume_number_bounds=number_bounds(cell,:,p)" in result
    assert "volume_number_bounds=number_bounds(c,:,pair)" in result
    # Rain diffusion remains a rain-specific source correction.
    assert "IF (p==3.AND.PRESENT(pr87_rain_diffusion_delta))" in result
    with pytest.raises(ValueError, match="frozen V22b"):
        TRANSFORM["extend_cloud_source_contract"](original + "\n")


def test_final_density_call_commits_cloud_and_rain_together():
    original = gzip.decompress((ARCHIVE / "solve_em.F.gz").read_bytes()).decode()
    result = TRANSFORM["extend_qn_density_call"](original)
    call = result.index("CALL pr87_qn_density_store")
    observer = result.index("CALL pr85_joint_stage_dump('RK_STAGE_END'", call)
    args = result[call:observer]
    for q, n in (("P_QC", "P_QNC"), ("P_QR", "P_QNR")):
        assert f"moist(ims,kms,jms,{q}),scalar(ims,kms,jms,{n})" in args
    assert "523.59881591796875,3.0,12000.0,500000.0" in args
    assert "12566.37109375,3.0,961.0,35000.0" in args
    assert "pr87_rain_density_store" not in result
    assert "cloud/rain density storage transaction rejected" in args
    with pytest.raises(ValueError, match="frozen V22b"):
        TRANSFORM["extend_qn_density_call"](original + "\n")


def test_cloud_public_return_uses_the_same_joint_store_before_host_consumption():
    original = gzip.decompress((ARCHIVE / "module_mp_kdm6.F.gz").read_bytes()).decode()
    result = TRANSFORM["extend_cloud_public_contract"](original)
    assert "pidnc/=523.59881591796875" in result
    assert "file='pr87_qn_public_store.raw'" in result
    assert "external :: pr87_number_public_store" in result
    assert "call pr87_number_public_store(qrs(i,k,1),nrs(i,k,1)" in result
    cloud = result.index("call pr87_number_public_store(qci(i,k,1),nci(i,k,1)")
    commit = result.index("nc(i,k,j) = number_value", cloud)
    section = result[cloud:commit]
    assert "pidnc,dmc,lamdacmin,lamdacmax" in section
    assert "PR87_CLOUD_PUBLIC_STORE_REJECT" in section
    assert "qc(i,k,j)=pr87_rain_q_public" in section
    assert "number_value=pr87_rain_n_public" in section
    assert "PR87_CLOUD_PUBLIC_STORE'" in section
    assert "pr87_rain_store_dq" in section and "pr87_rain_store_dn" in section
    with pytest.raises(ValueError, match="frozen V22b"):
        TRANSFORM["extend_cloud_public_contract"](original + "\n")
