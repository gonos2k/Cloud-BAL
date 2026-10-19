from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import pr87_rain_sedimentation as rain  # noqa: E402


OLD_HELPER = """SUBROUTINE pr85_kdm6_paired_sediment_column(a)
END SUBROUTINE pr85_kdm6_paired_sediment_column
"""

NEW_HELPER = """SUBROUTINE pr85_kdm6_paired_sediment_column(a,budget_unit,trace,valid,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max)
INTEGER, PARAMETER :: PR85_SED_ICE=1, PR85_SED_GRAUPEL=2, PR87_SED_RAIN=3
END SUBROUTINE pr85_kdm6_paired_sediment_column
"""


SOURCE_FIXTURE = """subroutine kdm6
   integer :: i,j,k
   do j = jts,jte
     call kdm62D(t,qci,qrs,nci,nrs,brs,rhox,cmg,den,p,delz,delt,g,cpd,cpv,ccn0,rd,rv,t0c, &
                 ep1,ep2,qmin,xls,xlv0,xlf0,den0,denr,cliq,cice,psat, &
                ,j                                            &
                ,xland(ims,j))
   enddo
end subroutine kdm6
subroutine kdm62D(t,qci,qrs,nci,nrs,brs,rhox,cmg,den,p,delz,delt,g,cpd,cpv,ccn0,rd,rv,t0c, &
                 ep1,ep2,qmin,xls,xlv0,xlf0,den0,denr,cliq,cice,psat, &
                   ,lat                                           &
                   ,slmsk)
   integer                                , intent(in   ) :: lat
   integer :: i,j,k
   integer :: pr85_g_unit, pr85_g_ios
   external :: pr85_kdm6_paired_sediment_column
   double precision, dimension(kts:kte) :: pr85_ice_qrate, pr85_ice_nrate
   logical :: pr85_g_valid
   call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep(i), &
        dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,3), &
        mass_velocity_rate(i,kts:kte,3),qrs(i,kts:kte,3),brs(i,kts:kte), &
        PR85_SED_GRAUPEL,qcrmin,pr85_brs_min,100.0,900.0, &
        pr85_g_qrate(kts:kte),pr85_g_brate(kts:kte), &
        pr85_g_unit,pr67_trace_this_call,pr85_g_valid)
   call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep_i(i), &
        dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,4), &
        number_velocity_rate(i,kts:kte,2),qci(i,kts:kte,2),nci(i,kts:kte,2), &
        PR85_SED_ICE,0.0,0.0,0.0,0.0,pr85_ice_qrate,pr85_ice_nrate, &
                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid)
      pr85_g_unit = 0
      do n = 1, mstepmax
        do i = its, ite
          pr85_g_qrate(kts:kte) = 0.0d0
          pr85_g_brate(kts:kte) = 0.0d0
          if (n.le.mstep(i)) then
            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,3), &
                 mass_velocity_rate(i,kts:kte,3),qrs(i,kts:kte,3),brs(i,kts:kte), &
                 PR85_SED_GRAUPEL,qcrmin,pr85_brs_min,100.0,900.0, &
                 pr85_g_qrate(kts:kte),pr85_g_brate(kts:kte), &
                 pr85_g_unit,pr67_trace_this_call,pr85_g_valid)
            if (.not.pr85_g_valid) error stop 'PR85 graupel sedimentation packet rejected'
            do k = kts, kte
              falk(i,k,3) = REAL(pr85_g_qrate(k))
              falkb(i,k) = REAL(pr85_g_brate(k))
            enddo
          endif
        enddo
        k = kte
        do i = its, ite
         if(n.le.mstep(i)) then
           falk(i,k,1) = dend(i,k)*qrs(i,k,1)*mass_velocity_rate(i,k,1)/mstep(i)
           falkn(i,k,1) = nrs(i,k,1)*number_velocity_rate(i,k,1)/mstep(i)
           fall(i,k,1) = fall(i,k,1)+falk(i,k,1)
           falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)
           qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)
           nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)
           fallb(i,k) = fallb(i,k)+falkb(i,k)
           falk(i,k,2) = dend(i,k)*qrs(i,k,2)*mass_velocity_rate(i,k,2)/mstep(i)
           fall(i,k,2) = fall(i,k,2)+falk(i,k,2)
           qrs(i,k,2) = max(qrs(i,k,2)-falk(i,k,2)*dtcld/dend(i,k),0.)
           fall(i,k,3) = fall(i,k,3)+falk(i,k,3)
         endif
       enddo
       do k = kte_in-1,kts,-1
         do i = its,ite
           if(n.le.mstep(i)) then
             falk(i,k,1) = dend(i,k)*qrs(i,k,1)*mass_velocity_rate(i,k,1)/mstep(i)
             falkn(i,k,1) = nrs(i,k,1)*number_velocity_rate(i,k,1)/mstep(i)
             fall(i,k,1) = fall(i,k,1)+falk(i,k,1)
             dqr(i,k) = min(falk(i,k,1)*dtcld/dend(i,k),qrs(i,k,1))
             dqr(i,k+1) = min(falk(i,k+1)*delz(i,k+1)/delz(i,k)              &
                          *dtcld/dend(i,k),qrs(i,k+1,1))
             falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)
             dnr(i,k) = min(falkn(i,k,1)*dtcld,nrs(i,k,1))
             dnr(i,k+1) = min(falkn(i,k+1,1)*delz(i,k+1)/delz(i,k)*dtcld,        &
                          nrs(i,k+1,1))
             nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)
             qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)
             fallb(i,k) = fallb(i,k)+falkb(i,k)
             falk(i,k,2) = dend(i,k)*qrs(i,k,2)*mass_velocity_rate(i,k,2)/mstep(i)
             fall(i,k,2) = fall(i,k,2)+falk(i,k,2)
             dqs(i,k) = min(falk(i,k,2)*dtcld/dend(i,k),qrs(i,k,2))
             qrs(i,k,2) = max(qrs(i,k,2)-dqs(i,k)+dqs(i,k+1),0.)
             fall(i,k,3) = fall(i,k,3)+falk(i,k,3)
            endif
          enddo
        enddo
      if (pr67_trace_this_call) close(pr85_g_unit,iostat=pr85_g_ios)
   end subroutine kdm62D
""" + OLD_HELPER


def test_rain_overlay_preserves_nonrain_fluxes_and_routes_paired_rates(monkeypatch: pytest.MonkeyPatch) -> None:
    source_hash = hashlib.sha256(SOURCE_FIXTURE.encode()).hexdigest()
    helper_hash = hashlib.sha256(OLD_HELPER.encode()).hexdigest()
    monkeypatch.setattr(rain, "V10_MODULE_SOURCE_SHA256", source_hash)
    monkeypatch.setattr(rain, "V10_EMBEDDED_HELPER_SHA256", helper_hash)

    output = rain.generate_rain_sedimentation(SOURCE_FIXTURE, NEW_HELPER)
    assert NEW_HELPER.strip() in output
    assert ",itimestep" in output
    assert "pr87_model_timestep,lat,dtcld" in output
    assert "pr85_g_valid,0.0,0.0,0.0,0.0)" in output
    assert "pr85_ice_valid,0.0,0.0,0.0,0.0)" in output
    assert "interface\n      subroutine pr85_kdm6_paired_sediment_column" in output
    assert "real, intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max" in output
    assert "external :: pr85_kdm6_paired_sediment_column" not in output
    assert "PR87_SED_RAIN,qcrmin,nrmin,0.0,0.0" in output
    assert "pidnr,dmr,lamdarmin,lamdarmax)" in output
    assert "DBLE(pidnr)/(DBLE(lamdarmax)**DBLE(dmr))" not in output
    assert "if (pr67_trace_this_call) then\n        open(newunit=pr87_rain_unit" not in output
    assert "open(newunit=pr87_rain_unit" in output
    assert "close(pr87_rain_unit,iostat=pr87_rain_ios)" in output
    assert "pr87_rain_unit,.true.,pr87_rain_valid" in output
    assert "pr85_g_unit,pr67_trace_this_call,pr85_g_valid" in output
    assert output.count("REAL(pr87_rain_qrate(k))") == 2
    assert output.count("REAL(pr87_rain_nrate(k))") == 2

    assert "qrs(i,k,1) = max(qrs(i,k,1)-falk(i,k,1)*dtcld/dend(i,k),0.)" not in output
    assert "nrs(i,k,1) = max(nrs(i,k,1)-falkn(i,k,1)*dtcld,0.)" not in output
    assert "qrs(i,k,1) = max(qrs(i,k,1)-dqr(i,k)+dqr(i,k+1),0.)" not in output
    assert "nrs(i,k,1) = max(nrs(i,k,1)-dnr(i,k)+dnr(i,k+1),0.)" not in output

    for preserved in (
        "fall(i,k,1) = fall(i,k,1)+falk(i,k,1)",
        "falln(i,k,1) = falln(i,k,1)+falkn(i,k,1)",
        "fallb(i,k) = fallb(i,k)+falkb(i,k)",
        "falk(i,k,2) = dend(i,k)*qrs(i,k,2)*mass_velocity_rate(i,k,2)/mstep(i)",
        "qrs(i,k,2) = max(qrs(i,k,2)-falk(i,k,2)*dtcld/dend(i,k),0.)",
        "falk(i,k,3) = REAL(pr85_g_qrate(k))",
        "falkb(i,k) = REAL(pr85_g_brate(k))",
    ):
        assert preserved in output


def test_rain_generator_rejects_source_and_helper_drift() -> None:
    with pytest.raises(ValueError, match="source identity mismatch"):
        rain.generate_rain_sedimentation("changed source", NEW_HELPER)
    with pytest.raises(ValueError, match="rain PSD arguments"):
        rain._validate_extended_helper(NEW_HELPER.replace(",rain_pidn,rain_power,rain_lambda_min,rain_lambda_max", ""))


def test_failure_diagnostic_is_only_inside_existing_rejection_branch() -> None:
    source_hash = hashlib.sha256(SOURCE_FIXTURE.encode()).hexdigest()
    helper_hash = hashlib.sha256(OLD_HELPER.encode()).hexdigest()
    # The production input identity remains pinned by the generator.  This
    # fixture isolates the failure-only callsite transform from that preimage.
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(rain, "V10_MODULE_SOURCE_SHA256", source_hash)
    monkeypatch.setattr(rain, "V10_EMBEDDED_HELPER_SHA256", helper_hash)
    try:
        generated = rain.generate_rain_sedimentation(SOURCE_FIXTURE, NEW_HELPER)
        traced = rain.add_rain_failure_diagnostic(generated)
    finally:
        monkeypatch.undo()

    assert traced.count("'PR87_RAIN_FAIL',pr87_model_timestep,i,lat,n,mstep(i)") == 1
    assert "dtcld,pidnr,dmr,lamdarmin,lamdarmax,qcrmin,nrmin" in traced
    assert "qrs(i,k,1),nrs(i,k,1),dend(i,k)," in traced
    assert "delz(i,k),mass_velocity_rate(i,k,1),number_velocity_rate(i,k,1)" in traced
    block = traced[traced.index("            if (.not.pr87_rain_valid) then"):]
    block = block[:block.index("          endif")]
    assert block.index("flush(pr87_rain_unit)") < block.index(
        "error stop 'PR87 rain sedimentation packet rejected'")
    assert "PR87_RAIN_FAIL" not in generated


def test_failure_diagnostic_requires_unique_unchanged_fatal_anchor() -> None:
    with pytest.raises(ValueError, match="rain packet rejection fatal"):
        rain.add_rain_failure_diagnostic("no rain callsite")
