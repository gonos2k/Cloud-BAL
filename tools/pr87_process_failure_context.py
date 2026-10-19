"""Add failure-only exact operand context to the V34 cold G search fatal."""

from __future__ import annotations

import hashlib


V34_KDM6_SHA256 = "2b10d9f15caa6c91a541428b19a6187bab7d75080e1ab67ae94b2435f7d928ce"
V36_KDM6_SHA256 = "4566a0c25cc20823a0fb07220ba0e646e3f3db6f42ffc954fc11924789de90c1"
V38_KDM6_SHA256 = "2a98262602d98b9288453ea0183e3ffe425c972779e012590317fc80ca11d73d"
V39_KDM6_SHA256 = "03dc6c3d96817187657212943f3aa1098480553514f90a5d16c74a873692e8b5"
V39_FINAL_KDM6_SHA256 = "6a7f6e154390ad6d5da8ca18ea4115ad66effa5b1dbdbf73754edd357b6b4293"


def add_process_failure_context(source: str) -> str:
    """Print the actual cold G search operands immediately before its fatal."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash not in (V34_KDM6_SHA256, V36_KDM6_SHA256, V38_KDM6_SHA256, V39_KDM6_SHA256):
        raise ValueError(f"unexpected KDM6 source hash: {actual_hash}")

    anchor = """            if (.not.rain_process_feasible) then
              if (.not.rain_bg_rates_feasible) then
"""
    diagnostic = """            if (.not.rain_process_feasible) then
              write(*,'(a,9(1x,i0))') 'PR87_GSEARCH_FAIL_META', &
                   pr87_model_timestep,lat,i,k,loop,n,rain_process_search_status, &
                   merge(1,0,rain_full_evap_pending(i,k)), &
                   merge(1,0,ice_full_sublimation_pending(i,k))
              write(*,'(a,26(1x,es26.17))') 'PR87_GSEARCH_FAIL_STATE', &
                   real(rain_q_fixed,8),real(rain_g_q_process,8), &
                   real(rain_n_fixed,8),real(rain_g_n_process,8), &
                   real(rain_bg_fixed,8),real(rain_g_bg_process,8), &
                   real(rain_t_fixed,8),real(rain_g_t_process,8), &
                   real(dry_carrier_density(i,k),8),real(pidnr,8),real(qmin,8), &
                   real(ncmin,8),real(qcrmin,8),real(dmr,8)
              write(*,'(a,16(1x,es26.17))') 'PR87_GSEARCH_FAIL_CONFIG', &
                   real(lamdarmin,8),real(lamdarmax,8),100.0_8,900.0_8, &
                   real(pidnc,8),real(dmc,8),real(lamdacmin,8),real(lamdacmax,8), &
                   real(pidni,8),real(dmi,8),real(lamdaimin,8),real(lamdaimax,8), &
                   real(rain_qv_stage,8),real(rain_g_qv_process,8), &
                   real(PR85_ICE_NATIVE_INACTIVE_MAX,8),real(rain_g_alpha,8)
              flush(6)
              if (.not.rain_bg_rates_feasible) then
"""
    if source.count(anchor) != 1:
        raise ValueError("expected one cold G process failure anchor")
    if "PR87_GSEARCH_FAIL_META" in source:
        raise ValueError("cold G process failure context already present")
    return source.replace(anchor, diagnostic, 1)


def add_ice_sedimentation_context(source: str) -> str:
    """Report timestep-2 stored ice PSD outliers at the sedimentation call."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != V39_FINAL_KDM6_SHA256:
        raise ValueError(f"unexpected V39 KDM6 source hash: {actual_hash}")

    declaration_anchor = "   integer                                , intent(in   ) :: lat\n"
    declarations = """   real :: pr87_ice_q_before(kts:kte),pr87_ice_n_before(kts:kte)
   real(kind=8) :: pr87_ice_diag_ratio,pr87_ice_diag_lower,pr87_ice_diag_upper
   real(kind=8) :: pr87_ice_diag_lower_tol,pr87_ice_diag_upper_tol
   integer :: pr87_ice_diag_bits(4),pr87_ice_diag_first
   logical :: pr87_ice_diag_column_written
"""
    if source.count(declaration_anchor) != 1:
        raise ValueError("KDM62D ice diagnostic declaration anchor missing or ambiguous")
    source = source.replace(declaration_anchor, declarations + declaration_anchor, 1)

    call_anchor = """            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep_i(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,4), &
                 number_velocity_rate(i,kts:kte,2),qci(i,kts:kte,2),nci(i,kts:kte,2), &
                 PR85_SED_ICE,0.0,0.0,0.0,0.0,pr85_ice_qrate,pr85_ice_nrate, &
                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid,0.0,0.0,0.0,0.0)
            if (.not.pr85_ice_valid) error stop 'PR85 ice sedimentation packet rejected'
"""
    instrumented = """            pr87_ice_q_before=qci(i,kts:kte,2)
            pr87_ice_n_before=nci(i,kts:kte,2)
            call pr85_kdm6_paired_sediment_column(kts,kte,i,lat,n,dtcld,mstep_i(i), &
                 dend(i,kts:kte),delz(i,kts:kte),mass_velocity_rate(i,kts:kte,4), &
                 number_velocity_rate(i,kts:kte,2),qci(i,kts:kte,2),nci(i,kts:kte,2), &
                 PR85_SED_ICE,0.0,0.0,0.0,0.0,pr85_ice_qrate,pr85_ice_nrate, &
                 pr85_ice_unit,pr67_trace_this_call,pr85_ice_valid,0.0,0.0,0.0,0.0)
            if (.not.pr85_ice_valid) error stop 'PR85 ice sedimentation packet rejected'
            if (pr87_model_timestep.eq.2) then
              pr87_ice_diag_column_written=.false.
              do k=kts,kte
                if (.not.all(ieee_is_finite([qci(i,k,2),nci(i,k,2),dend(i,k)]))) cycle
                if (qci(i,k,2).le.0.0 .or. nci(i,k,2).le.0.0 .or. dend(i,k).le.0.0) cycle
                pr87_ice_diag_ratio=DBLE(dend(i,k))*DBLE(qci(i,k,2))/DBLE(nci(i,k,2))
                pr87_ice_diag_lower=DBLE(1570.79638671875)/DBLE(1820000.0)**3
                pr87_ice_diag_upper=DBLE(1570.79638671875)/DBLE(9080.0)**3
                pr87_ice_diag_lower_tol=8.0d0*ABS(DBLE(SPACING(REAL(pr87_ice_diag_lower))))
                pr87_ice_diag_upper_tol=8.0d0*ABS(DBLE(SPACING(REAL(pr87_ice_diag_upper))))
                if (pr87_ice_diag_ratio.ge.pr87_ice_diag_lower-pr87_ice_diag_lower_tol .and. &
                    pr87_ice_diag_ratio.le.pr87_ice_diag_upper+pr87_ice_diag_upper_tol) cycle
                write(*,'(a,7(1x,i0),1p,7(1x,es26.17))') 'PR87_ICE_SED_OUTLIER', &
                     pr87_model_timestep,lat,i,k,loop,n,mstep_i(i),dtcld,real(qmin,8), &
                     pr87_ice_diag_ratio,pr87_ice_diag_lower,pr87_ice_diag_upper, &
                     pr87_ice_diag_lower_tol,pr87_ice_diag_upper_tol
                pr87_ice_diag_bits=[transfer(pr87_ice_q_before(k),0), &
                     transfer(pr87_ice_n_before(k),0),transfer(qci(i,k,2),0), &
                     transfer(nci(i,k,2),0)]
                write(*,'(a,4(1x,z8.8),1p,8(1x,es26.17))') 'PR87_ICE_SED_STATE', &
                     pr87_ice_diag_bits,pr87_ice_q_before(k),pr87_ice_n_before(k), &
                     qci(i,k,2),nci(i,k,2),dend(i,k),delz(i,k), &
                     mass_velocity_rate(i,k,4),number_velocity_rate(i,k,2)
                if (.not.pr87_ice_diag_column_written) then
                  write(*,'(a,6(1x,i0),1p,2(1x,es26.17))') 'PR87_ICE_SED_COLUMN', &
                       pr87_model_timestep,lat,i,loop,n,mstep_i(i),dtcld,real(qmin,8)
                  do pr87_ice_diag_first=kts,kte
                    pr87_ice_diag_bits=[transfer(pr87_ice_q_before(pr87_ice_diag_first),0), &
                         transfer(pr87_ice_n_before(pr87_ice_diag_first),0), &
                         transfer(qci(i,pr87_ice_diag_first,2),0), &
                         transfer(nci(i,pr87_ice_diag_first,2),0)]
                    write(*,'(a,2(1x,i0),4(1x,z8.8),1p,8(1x,es26.17))') &
                         'PR87_ICE_SED_REPLAY',pr87_model_timestep,pr87_ice_diag_first, &
                         pr87_ice_diag_bits,pr87_ice_q_before(pr87_ice_diag_first), &
                         pr87_ice_n_before(pr87_ice_diag_first),qci(i,pr87_ice_diag_first,2), &
                         nci(i,pr87_ice_diag_first,2),dend(i,pr87_ice_diag_first), &
                         delz(i,pr87_ice_diag_first),mass_velocity_rate(i,pr87_ice_diag_first,4), &
                         number_velocity_rate(i,pr87_ice_diag_first,2)
                  enddo
                  pr87_ice_diag_column_written=.true.
                endif
                flush(6)
              enddo
            endif
"""
    if source.count(call_anchor) != 1:
        raise ValueError("KDM62D ice sedimentation call anchor missing or ambiguous")
    if "PR87_ICE_SED_OUTLIER" in source:
        raise ValueError("ice sedimentation context already present")
    return source.replace(call_anchor, instrumented, 1)


def add_ice_process_endpoint_context(source: str) -> str:
    """Enable existing cold/warm budget rows for timestep-2 small ice outliers."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != V39_FINAL_KDM6_SHA256:
        raise ValueError(f"unexpected V39 KDM6 source hash: {actual_hash}")
    if "PR87_KDM6_COLD_T2" in source or "PR87_KDM6_WARM_T2" in source:
        raise ValueError("ice process endpoint context already present")

    declaration_anchor = "   integer                                , intent(in   ) :: lat\n"
    declarations = """   logical :: pr87_ice_process_diag
   real(kind=8) :: pr87_ice_process_ratio,pr87_ice_process_lower,pr87_ice_process_upper
   real(kind=8) :: pr87_ice_process_lower_tol,pr87_ice_process_upper_tol
   character(len=20) :: pr87_ice_warm_label
"""
    if source.count(declaration_anchor) != 1:
        raise ValueError("KDM62D ice process diagnostic declaration anchor missing or ambiguous")
    source = source.replace(declaration_anchor, declarations + declaration_anchor, 1)

    cold_anchor = """            if (.false.) then
            write(pr85_cold_unit,'(a,8i8,1x,l1,1p,*(1x,e24.16))',iostat=pr85_cold_ios) &
                 'PR85_KDM6_COLD',i,lat,k,loop,rain_ng_search_status, &
"""
    cold_diagnostic = """            pr87_ice_process_diag=.false.
            if (pr87_model_timestep.eq.2) then
              if (all(ieee_is_finite([qci(i,k,2),nci(i,k,2),dry_carrier_density(i,k)]))) then
                if (qci(i,k,2).gt.0.0 .and. qci(i,k,2).le.1.0e-14 .and. &
                    nci(i,k,2).gt.0.0 .and. dry_carrier_density(i,k).gt.0.0) then
                  pr87_ice_process_ratio=DBLE(dry_carrier_density(i,k))* &
                       DBLE(qci(i,k,2))/DBLE(nci(i,k,2))
                  pr87_ice_process_lower=DBLE(1570.79638671875)/DBLE(1820000.0)**3
                  pr87_ice_process_upper=DBLE(1570.79638671875)/DBLE(9080.0)**3
                  pr87_ice_process_lower_tol=8.0d0*ABS(DBLE(SPACING(REAL(pr87_ice_process_lower))))
                  pr87_ice_process_upper_tol=8.0d0*ABS(DBLE(SPACING(REAL(pr87_ice_process_upper))))
                  pr87_ice_process_diag=pr87_ice_process_ratio.lt. &
                       pr87_ice_process_lower-pr87_ice_process_lower_tol .or. &
                       pr87_ice_process_ratio.gt.pr87_ice_process_upper+pr87_ice_process_upper_tol
                endif
              endif
            endif
            if (pr87_ice_process_diag) then
            write(pr85_cold_unit,'(a,9i8,1x,l1,1p,*(1x,e24.16))',iostat=pr85_cold_ios) &
                 'PR87_KDM6_COLD_T2',pr87_model_timestep,i,lat,k,loop,rain_ng_search_status, &
"""
    if source.count(cold_anchor) != 1:
        raise ValueError("existing cold budget write anchor missing or ambiguous")
    source = source.replace(cold_anchor, cold_diagnostic, 1)

    warm_condition = """            ! Existing full v17 ledgers remain the reference.
            ! Sparse PR87 NO_POSITIVE_WARM_STEP trace: status 1 only.
            if (rain_warm_search_status.eq.1) then
            write(pr85_warm_unit,'(a,7i8,1x,2l1,1p,*(1x,e24.16))',iostat=pr85_warm_ios) &
                 'WARM',i,lat,k,loop,rain_warm_search_status,rain_warm_retry, &
"""
    warm_diagnostic = """            ! Existing full v17 ledgers remain the reference.
            ! Add timestep-2 metadata when the small ice endpoint is outside its PSD cone.
            pr87_ice_process_diag=.false.
            if (pr87_model_timestep.eq.2) then
              if (all(ieee_is_finite([rain_warm_q_after(2),rain_warm_n_after(2), &
                                     dry_carrier_density(i,k)]))) then
                if (rain_warm_q_after(2).gt.0.0 .and. rain_warm_q_after(2).le.1.0e-14 .and. &
                    rain_warm_n_after(2).gt.0.0 .and. dry_carrier_density(i,k).gt.0.0) then
                  pr87_ice_process_ratio=DBLE(dry_carrier_density(i,k))* &
                       DBLE(rain_warm_q_after(2))/DBLE(rain_warm_n_after(2))
                  pr87_ice_process_lower=DBLE(1570.79638671875)/DBLE(1820000.0)**3
                  pr87_ice_process_upper=DBLE(1570.79638671875)/DBLE(9080.0)**3
                  pr87_ice_process_lower_tol=8.0d0*ABS(DBLE(SPACING(REAL(pr87_ice_process_lower))))
                  pr87_ice_process_upper_tol=8.0d0*ABS(DBLE(SPACING(REAL(pr87_ice_process_upper))))
                  pr87_ice_process_diag=pr87_ice_process_ratio.lt. &
                       pr87_ice_process_lower-pr87_ice_process_lower_tol .or. &
                       pr87_ice_process_ratio.gt.pr87_ice_process_upper+pr87_ice_process_upper_tol
                endif
              endif
            endif
            pr87_ice_warm_label='WARM'
            if (pr87_ice_process_diag) pr87_ice_warm_label='PR87_KDM6_WARM_T2'
            if (rain_warm_search_status.eq.1 .or. pr87_ice_process_diag) then
            write(pr85_warm_unit,'(a,7i8,1x,2l1,1p,*(1x,e24.16))',iostat=pr85_warm_ios) &
                 pr87_ice_warm_label,i,lat,k,loop,rain_warm_search_status, &
"""
    if source.count(warm_condition) != 1:
        raise ValueError("existing warm budget write anchor missing or ambiguous")
    source = source.replace(warm_condition, warm_diagnostic, 1)

    return source
