from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "tools/pr101_cloud_thermo_source.py"


def load_module():
    spec = importlib.util.spec_from_file_location("pr101_cloud_thermo_source", MODULE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def source():
    return """   real :: cloud_evap_extent
   call liquid_begin(its,ite)
       cpm(i,k) = cpmcal(q(i,k))
       xl(i,k) = xlcal(t(i,k))
   call liquid_end(lat,its,ite)
     pr100_qc_open=.true.
          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))
          qs(i,k,1) = min(qs(i,k,1),0.99*p(i,k))
          qs(i,k,1) = ep2 * qs(i,k,1) / (p(i,k) - qs(i,k,1))
          qs(i,k,1) = max(qs(i,k,1),qmin)
          work1(i,k,1) = conden(t(i,k),q(i,k),qs(i,k,1),xl(i,k),cpm(i,k))
          pcond(i,k) = min(max(work1(i,k,1)/dtcld,0.),max(q(i,k),0.)/dtcld)
          if(qci(i,k,1).gt.0. .and. work1(i,k,1).lt.0.)                        &
            pcond(i,k) = max(work1(i,k,1),-qci(i,k,1))/dtcld
          if(full_cloud_evap) then
            q(i,k) = q(i,k)+cloud_evap_extent
            qci(i,k,1) = 0.
            t(i,k) = t(i,k)-cloud_evap_extent*xl(i,k)/cpm(i,k)
          else
            q(i,k) = q(i,k)-pcond(i,k)*dtcld
            qci(i,k,1) = max(qci(i,k,1)+pcond(i,k)*dtcld,0.)
            t(i,k) = t(i,k)+pcond(i,k)*xl(i,k)/cpm(i,k)*dtcld
          endif
          if(full_cloud_evap) pr97_extent=-cloud_evap_extent
     close(pr100_qc_unit)
        REAL FUNCTION GAMMLN(x)
"""


def test_transform_preserves_physics_and_captures_source_state(source):
    module = load_module()
    generated = module.instrument_thermodynamics(source)

    for assignment in (
        "qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))",
        "pcond(i,k) = min(max(work1(i,k,1)/dtcld,0.),max(q(i,k),0.)/dtcld)",
        "q(i,k) = q(i,k)-pcond(i,k)*dtcld",
        "qci(i,k,1) = max(qci(i,k,1)+pcond(i,k)*dtcld,0.)",
        "t(i,k) = t(i,k)+pcond(i,k)*xl(i,k)/cpm(i,k)*dtcld",
    ):
        assert generated.count(assignment) == 1
    assert "pr101_es=qs(i,k,1)" in generated
    assert "pr101_t_before=t(i,k)" in generated
    assert "pr101_source_extent=cloud_evap_extent" in generated
    assert "pr101_source_extent=-pcond(i,k)*dtcld" in generated
    assert "pr101_qv_after=q(i,k)" in generated
    assert "pr101_qc_after=qci(i,k,1)" in generated
    assert "pr101_t_after=t(i,k)" in generated
    assert "full_cloud_evap,pr101_t_before,p(i,k)" in generated
    assert "double precision :: pr101_work1,pr101_e_request" in generated
    assert "pr101_work1=work1(i,k,1)" in generated
    assert "pr101_e_request=max(-pr101_work1,0.d0)" in generated
    assert "double precision, intent(in) :: work" in generated
    assert "pr101_bounded_e=max(-pcond(i,k)*dtcld,0.)" in generated
    assert "pr101_liquid_qs(pr101_xl_basis_t(i,k)" in generated
    assert "pr101_liquid_qs(pr101_t_after" in generated
    assert "pr101_rh_initial=max(pr101_cpm_basis_q(i,k)/pr101_qs_initial,qmin)" in generated
    assert "'PR101THERMO_LIQUID'" in generated


@pytest.mark.parametrize("anchor", [
    "          qs(i,k,1)=psat*exp(log(tr)*(xa))*exp(xb*(1.-tr))\n",
    "          if(full_cloud_evap) pr97_extent=-cloud_evap_extent\n",
])
def test_transform_rejects_missing_source_anchor(source, anchor):
    with pytest.raises(ValueError, match="expected one"):
        load_module().instrument_thermodynamics(source.replace(anchor, "", 1))
