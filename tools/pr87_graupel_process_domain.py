"""Keep process-fraction endpoints inside the native ProgB graupel domain."""

from __future__ import annotations

import hashlib


V31_KDM6_SHA256 = "9cb8d19bf676771e5bfd717d07cdaf43b4bc63912b0b7869b977fbd0f2ac1397"


def extend_graupel_process_domain(source: str) -> str:
    """Add the existing ProgB transient boundary to default rain-process search."""
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash != V31_KDM6_SHA256:
        raise ValueError(f"unexpected V31 KDM6 source hash: {actual_hash}")

    fraction_start = source.index("    subroutine kdm6_rain_process_fraction(")
    fraction_end = source.index("    end subroutine kdm6_rain_process_fraction", fraction_start)
    fraction = source[fraction_start:fraction_end]

    prune_call = (
        "        call interval_constraints(midpoint,lower,upper,interval_valid)\n"
        "        if (.not.interval_valid) cycle\n"
    )
    prune_call_new = (
        "        call interval_constraints(midpoint,lower,upper,interval_valid)\n"
        "        if (.not.interval_valid) cycle\n"
        "        if (.not.pair_only) then\n"
        "          if (no_storable_rain_interval(lower,upper)) cycle\n"
        "        endif\n"
    )
    if fraction.count(prune_call) != 1:
        raise ValueError("full-PSD interval-prune call anchor missing or ambiguous")
    fraction = fraction.replace(prune_call, prune_call_new, 1)

    interval_anchor = "      subroutine interval_constraints(sample,lo,hi,valid_interval)\n"
    interval_helper = """      logical function no_storable_rain_interval(lo,hi)
        real(kind=8), intent(in) :: lo,hi
        real :: alpha_first,alpha_last,q_first,q_last,n_first,n_last
        real(kind=8) :: q_min_store,q_max_store,n_min_store,n_max_store
        real(kind=8) :: lower_number,upper_number

        no_storable_rain_interval=.false.
        if (.not.all(ieee_is_finite([lo,hi]))) return
        if (lo.gt.hi) return
        alpha_first=real(lo)
        if (.not.ieee_is_finite(alpha_first)) return
        if (real(alpha_first,8).lt.lo) alpha_first=nearest(alpha_first,1.0)
        alpha_last=real(hi)
        if (.not.ieee_is_finite(alpha_last)) return
        if (real(alpha_last,8).gt.hi) alpha_last=nearest(alpha_last,-1.0)
        if (.not.all(ieee_is_finite([alpha_first,alpha_last]))) return
        if (real(alpha_first,8).gt.hi .or. real(alpha_last,8).lt.lo .or. &
            alpha_first.gt.alpha_last) then
          no_storable_rain_interval=.true.
          return
        endif

        ! Rounded affine endpoint extrema enclose all stored REAL32 Q/N here.
        ! Requiring positive Q excludes exact absence from this rejection proof.
        q_first=q_fixed(3)+alpha_first*q_process(3)
        q_last=q_fixed(3)+alpha_last*q_process(3)
        n_first=n_fixed(3)+alpha_first*n_process(3)
        n_last=n_fixed(3)+alpha_last*n_process(3)
        if (.not.all(ieee_is_finite([q_first,q_last,n_first,n_last]))) return
        q_min_store=real(min(q_first,q_last),8)
        q_max_store=real(max(q_first,q_last),8)
        n_min_store=real(min(n_first,n_last),8)
        n_max_store=real(max(n_first,n_last),8)
        if (.not.all(ieee_is_finite([q_min_store,q_max_store,n_min_store,n_max_store]))) return
        if (q_min_store.le.0.0d0) return
        lower_number=rain_min*q_min_store
        upper_number=rain_max*q_max_store
        if (.not.all(ieee_is_finite([lower_number,upper_number]))) return
        no_storable_rain_interval=n_min_store.gt.upper_number .or. &
                                  n_max_store.lt.lower_number
      end function no_storable_rain_interval

"""
    if fraction.count(interval_anchor) != 1:
        raise ValueError("full-PSD interval-prune helper anchor missing or ambiguous")
    fraction = fraction.replace(interval_anchor, interval_helper + interval_anchor, 1)

    old_breakpoints = (
        "      if (pair_only) then\n"
        "        call add_breakpoint(q0(5),dq(5),real(qcrmin,8))\n"
        "        call add_breakpoint(bg0,dbg,real(1.0e-15,8))\n"
        "      endif\n"
    )
    new_breakpoints = (
        "      call add_breakpoint(q0(5),dq(5),real(qcrmin,8))\n"
        "      call add_breakpoint(bg0,dbg,real(1.0e-15,8))\n"
    )
    if fraction.count(old_breakpoints) != 1:
        raise ValueError("fraction graupel breakpoint anchor missing or ambiguous")
    fraction = fraction.replace(old_breakpoints, new_breakpoints, 1)

    interval_anchor = (
        "        call clip(q0(5)/real(rho_min,8)-bg0,dq(5)/real(rho_min,8)-dbg,lo,hi,valid_interval)\n"
        "        if (lo.gt.hi) valid_interval=.false.\n"
    )
    interval_new = (
        "        call clip(q0(5)/real(rho_min,8)-bg0,dq(5)/real(rho_min,8)-dbg,lo,hi,valid_interval)\n"
        "        if (qm(5).gt.0.0d0 .and. bm.gt.0.0d0 .and. &\n"
        "            qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)) &\n"
        "          valid_interval=.false.\n"
        "        if (lo.gt.hi) valid_interval=.false.\n"
    )
    if fraction.count(interval_anchor) != 1:
        raise ValueError("full-PSD interval graupel anchor missing or ambiguous")
    fraction = fraction.replace(interval_anchor, interval_new, 1)
    source = source[:fraction_start] + fraction + source[fraction_end:]

    state_start = source.index("subroutine kdm6_rain_process_state_valid(")
    state_end = source.index("end subroutine kdm6_rain_process_state_valid", state_start)
    state = source[state_start:state_end]
    state_anchor = (
        "      if (real(bg,8).lt.real(q(5),8)/real(rho_max,8) .or. &\n"
        "          real(bg,8).gt.real(q(5),8)/real(rho_min,8)) then\n"
        "        if (present(failure_reason)) failure_reason=9\n"
        "        return\n"
        "      endif\n"
        "      valid=.true.\n"
    )
    state_new = (
        "      if (q(5).gt.0.0 .or. bg.gt.0.0) then\n"
        "        if (q(5).le.0.0 .or. bg.le.0.0) then\n"
        "          if (present(failure_reason)) failure_reason=9\n"
        "          return\n"
        "        endif\n"
        "        if (real(q(5),8)/real(bg,8).lt.real(rho_min,8) .or. &\n"
        "            real(q(5),8)/real(bg,8).gt.real(rho_max,8)) then\n"
        "          if (present(failure_reason)) failure_reason=9\n"
        "          return\n"
        "        endif\n"
        "        if (q(5).le.qcrmin .and. bg.le.real(1.0e-15,8)) then\n"
        "          if (present(failure_reason)) failure_reason=4\n"
        "          return\n"
        "        endif\n"
        "      endif\n"
        "      valid=.true.\n"
    )
    if state.count(state_anchor) != 1:
        raise ValueError("default state-validator graupel anchor missing or ambiguous")
    state = state.replace(state_anchor, state_new, 1)
    source = source[:state_start] + state + source[state_end:]

    melt_declarations_anchor = "   logical :: rain_composite_valid\n"
    melt_declarations = """   logical :: rain_composite_valid
   real :: pr87_gmelt_q_fixed(5),pr87_gmelt_q_process(5),pr87_gmelt_q_after(5)
   real :: pr87_gmelt_n_fixed(3),pr87_gmelt_n_process(3),pr87_gmelt_n_after(3)
   real :: pr87_gmelt_bg_fixed,pr87_gmelt_bg_process,pr87_gmelt_bg_after
   real :: pr87_gmelt_t_fixed,pr87_gmelt_t_process,pr87_gmelt_t_after,pr87_gmelt_alpha
   real :: pr87_gmelt_t_ratio,pr87_gmelt_gfac_product
   double precision :: pr87_gmelt_bg_delta64,pr87_gmelt_rate64
   double precision :: pr87_gmelt_mass_residual,pr87_gmelt_volume_residual
   double precision :: pr87_gmelt_number_residual,pr87_gmelt_temperature_residual
   logical :: pr87_gmelt_feasible,pr87_gmelt_endpoint_valid,pr87_gmelt_base_valid
   integer :: pr87_gmelt_search_status,pr87_gmelt_failure_reason
   integer :: pr87_gmelt_unit,pr87_gmelt_ios
"""
    if source.count(melt_declarations_anchor) != 1:
        raise ValueError("graupel melt transaction declaration anchor missing or ambiguous")
    source = source.replace(melt_declarations_anchor, melt_declarations, 1)

    melt_anchor = """            if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.0.) then

              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))           &
                       *rslopemu(i,k,3)
              pgmlt(i,k) = (xka(t(i,k),gas_density(i,k)))/xlf*(t0c-t(i,k))                   &
                           *pi/2.*((precg1)*n0go(i,k)*rslope2(i,k,3)*rslopemu(i,k,3) &
                           +(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/dry_carrier_density(i,k)
              pgmlt(i,k) = min(max(pgmlt(i,k)*dtcld,-qrs(i,k,3)),0.)




              if (progb_status(i,k) == PROGB_PSD_ACTIVE .and. qrs(i,k,3) .gt.qcrmin) then
                gfac = (rslope(i,k,3))*n0go(i,k)/qrs(i,k,3)
                nrs(i,k,1) = nrs(i,k,1) - gfac*pgmlt(i,k)
              endif
              qrs(i,k,3) = qrs(i,k,3) + pgmlt(i,k)
              qrs(i,k,1) = qrs(i,k,1) - pgmlt(i,k)
              t(i,k) = t(i,k) + xlf/cpm(i,k)*pgmlt(i,k)
              if (progb_status(i,k) /= PROGB_PSD_ACTIVE) &
                error stop 'ProgB status invalid for melting volume'
              brs(i,k) = brs(i,k) + (pgmlt(i,k)/rhox(i,k))
            endif
"""
    melt_replacement = """            if(progb_status(i,k)==PROGB_PSD_ACTIVE .and. qrs(i,k,3).gt.0.) then
              coeres = (rslope2(i,k,3))*sqrt(rslope(i,k,3)*rslopeb(i,k,3))           &
                       *rslopemu(i,k,3)
              pgmlt(i,k) = (xka(t(i,k),gas_density(i,k)))/xlf*(t0c-t(i,k))                   &
                           *pi/2.*((precg1)*n0go(i,k)*rslope2(i,k,3)*rslopemu(i,k,3) &
                           +(precg2(i,k))*n0go(i,k)*work2(i,k)*coeres)/dry_carrier_density(i,k)
              pgmlt(i,k) = min(max(pgmlt(i,k)*dtcld,-qrs(i,k,3)),0.)
              if (progb_status(i,k) /= PROGB_PSD_ACTIVE) &
                error stop 'ProgB status invalid for melting volume'

              if (pgmlt(i,k) .lt. 0.0) then
                if (.not.ieee_is_finite(qrs(i,k,3))) &
                  error stop 'KDM6 graupel melt donor mass is nonfinite'
                if (qrs(i,k,3).le.0.0) &
                  error stop 'KDM6 graupel melt donor mass is invalid'
                if (.not.ieee_is_finite(brs(i,k))) &
                  error stop 'KDM6 graupel melt volume operands are invalid'
                if (.not.ieee_is_finite(pgmlt(i,k))) &
                  error stop 'KDM6 graupel melt volume operands are invalid'
                pr87_gmelt_q_fixed=[qci(i,k,1),qci(i,k,2),qrs(i,k,1),qrs(i,k,2),qrs(i,k,3)]
                pr87_gmelt_n_fixed=[nci(i,k,1),nci(i,k,2),nrs(i,k,1)]
                pr87_gmelt_bg_fixed=brs(i,k)
                pr87_gmelt_t_fixed=t(i,k)
                pr87_gmelt_q_process=0.0
                pr87_gmelt_n_process=0.0
                pr87_gmelt_q_process(3)=-pgmlt(i,k)
                pr87_gmelt_q_process(5)=pgmlt(i,k)
                if (qrs(i,k,3) .gt. qcrmin) then
                  if (.not.ieee_is_finite(rslope(i,k,3))) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  if (.not.ieee_is_finite(n0go(i,k))) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  pr87_gmelt_rate64=DBLE(rslope(i,k,3))*DBLE(n0go(i,k))
                  if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt number factor overflow'
                  pr87_gmelt_gfac_product=REAL(pr87_gmelt_rate64)
                  if (.not.ieee_is_finite(qrs(i,k,3))) &
                    error stop 'KDM6 graupel melt donor mass is nonfinite'
                  if (qrs(i,k,3).le.0.0) &
                    error stop 'KDM6 graupel melt donor mass is invalid'
                  pr87_gmelt_rate64=DBLE(pr87_gmelt_gfac_product)/DBLE(qrs(i,k,3))
                  if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                    error stop 'KDM6 graupel melt number factor is nonfinite'
                  if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt number factor overflow'
                  gfac=REAL(pr87_gmelt_rate64)
                  pr87_gmelt_rate64=-DBLE(gfac)*DBLE(pgmlt(i,k))
                  if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                    error stop 'KDM6 graupel melt number rate is nonfinite'
                  if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt number rate overflow'
                  pr87_gmelt_n_process(3)=REAL(pr87_gmelt_rate64)
                endif
                if (pgmlt(i,k) .eq. -qrs(i,k,3)) then
                  pr87_gmelt_bg_process=-brs(i,k)
                else
                  pr87_gmelt_bg_delta64=DBLE(pgmlt(i,k))*DBLE(brs(i,k))/DBLE(qrs(i,k,3))
                  if (.not.ieee_is_finite(pr87_gmelt_bg_delta64)) &
                    error stop 'KDM6 graupel melt volume rate is nonfinite'
                  if (ABS(pr87_gmelt_bg_delta64).gt.DBLE(HUGE(0.0))) &
                    error stop 'KDM6 graupel melt volume rate overflow'
                  pr87_gmelt_bg_process=REAL(pr87_gmelt_bg_delta64)
                endif
                if (.not.ieee_is_finite(xlf)) &
                  error stop 'KDM6 graupel melt heat capacity is invalid'
                if (.not.ieee_is_finite(cpm(i,k))) &
                  error stop 'KDM6 graupel melt heat capacity is invalid'
                if (cpm(i,k).le.0.0) &
                  error stop 'KDM6 graupel melt heat capacity is invalid'
                pr87_gmelt_rate64=DBLE(xlf)/DBLE(cpm(i,k))
                if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                  error stop 'KDM6 graupel melt temperature ratio is nonfinite'
                if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                  error stop 'KDM6 graupel melt temperature ratio overflow'
                pr87_gmelt_t_ratio=REAL(pr87_gmelt_rate64)
                pr87_gmelt_rate64=DBLE(pr87_gmelt_t_ratio)*DBLE(pgmlt(i,k))
                if (.not.ieee_is_finite(pr87_gmelt_rate64)) &
                  error stop 'KDM6 graupel melt temperature rate is nonfinite'
                if (ABS(pr87_gmelt_rate64).gt.DBLE(HUGE(0.0))) &
                  error stop 'KDM6 graupel melt temperature rate overflow'
                pr87_gmelt_t_process=REAL(pr87_gmelt_rate64)

                call kdm6_rain_process_fraction(pr87_gmelt_q_fixed,pr87_gmelt_q_process, &
                     pr87_gmelt_n_fixed,pr87_gmelt_n_process,pr87_gmelt_bg_fixed, &
                     pr87_gmelt_bg_process,pr87_gmelt_t_fixed,pr87_gmelt_t_process, &
                     .FALSE.,dry_carrier_density(i,k),pidnr,qmin,ncmin, &
                     qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                     lamdacmax,pidni,dmi,lamdaimin,lamdaimax,pr87_gmelt_alpha, &
                     pr87_gmelt_feasible,pr87_gmelt_search_status, &
                     consumer_pair_only=.TRUE., &
                     ice_sublimation_pending=.FALSE.)
                if (.not.pr87_gmelt_feasible) then
                  if (pr87_gmelt_search_status .eq. 1) then
                    call kdm6_rain_process_state_valid(pr87_gmelt_q_fixed, &
                         pr87_gmelt_n_fixed,pr87_gmelt_bg_fixed,pr87_gmelt_t_fixed, &
                         dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                         lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                         lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                         pr87_gmelt_base_valid,.FALSE., &
                         consumer_pair_only=.TRUE., &
                         ice_sublimation_pending=.FALSE.)
                    if (.not.pr87_gmelt_base_valid) &
                      error stop 'KDM6 graupel melt has invalid base state'
                    pr87_gmelt_alpha=0.0
                  else
                    error stop 'KDM6 graupel melt fraction search failed'
                  endif
                endif

                pr87_gmelt_q_after=pr87_gmelt_q_fixed+pr87_gmelt_alpha*pr87_gmelt_q_process
                pr87_gmelt_n_after=pr87_gmelt_n_fixed+pr87_gmelt_alpha*pr87_gmelt_n_process
                pr87_gmelt_bg_after=pr87_gmelt_bg_fixed+ &
                     pr87_gmelt_alpha*pr87_gmelt_bg_process
                pr87_gmelt_t_after=pr87_gmelt_t_fixed+pr87_gmelt_alpha*pr87_gmelt_t_process
                call kdm6_rain_process_state_valid(pr87_gmelt_q_after,pr87_gmelt_n_after, &
                     pr87_gmelt_bg_after,pr87_gmelt_t_after,dry_carrier_density(i,k),pidnr, &
                     qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc, &
                     lamdacmin,lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                     pr87_gmelt_endpoint_valid,.FALSE., &
                     consumer_pair_only=.TRUE., &
                     ice_sublimation_pending=.FALSE., &
                     failure_reason=pr87_gmelt_failure_reason)
                if (.not.pr87_gmelt_endpoint_valid) &
                  error stop 'KDM6 graupel melt candidate failed stored-state validation'

                pr87_gmelt_mass_residual= &
                     DBLE(pr87_gmelt_q_after(5))-DBLE(pr87_gmelt_q_fixed(5))+ &
                     DBLE(pr87_gmelt_q_after(3))-DBLE(pr87_gmelt_q_fixed(3))
                pr87_gmelt_volume_residual= &
                     DBLE(pr87_gmelt_bg_after)-DBLE(pr87_gmelt_bg_fixed)- &
                     DBLE(pr87_gmelt_alpha)*DBLE(pr87_gmelt_bg_process)
                pr87_gmelt_number_residual= &
                     DBLE(pr87_gmelt_n_after(3))-DBLE(pr87_gmelt_n_fixed(3))- &
                     DBLE(pr87_gmelt_alpha)*DBLE(pr87_gmelt_n_process(3))
                pr87_gmelt_temperature_residual= &
                     DBLE(pr87_gmelt_t_after)-DBLE(pr87_gmelt_t_fixed)- &
                     DBLE(pr87_gmelt_alpha)*DBLE(pr87_gmelt_t_process)
                pr87_gmelt_unit=0
                pr87_gmelt_ios=0
                open(newunit=pr87_gmelt_unit,file='pr87_graupel_melt.raw', &
                     form='formatted',status='unknown',position='append',action='write', &
                     iostat=pr87_gmelt_ios)
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger open failed'
                write(pr87_gmelt_unit,'(a)',iostat=pr87_gmelt_ios) &
                     '# PR87_GRAUPEL_MELT: i,lat,k,loop,search_status,feasible; '// &
                     'alpha,dt; QG before/proposed/approved/after; BG before/proposed/approved/after; '// &
                     'QR before/proposed/approved/after; NR before/proposed/approved/after; '// &
                     'T before/proposed/approved/after; signed storage residuals: kg/kg-dry,m3/kg-dry,#/m3,K'
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger header failed'
                write(pr87_gmelt_unit,'(a,5i8,l1,1p,26e24.16)',iostat=pr87_gmelt_ios) &
                     'PR87_GRAUPEL_MELT',i,lat,k,loop,pr87_gmelt_search_status, &
                     pr87_gmelt_feasible,pr87_gmelt_alpha,dtcld, &
                     pr87_gmelt_q_fixed(5),pr87_gmelt_q_process(5), &
                     pr87_gmelt_alpha*pr87_gmelt_q_process(5),pr87_gmelt_q_after(5), &
                     pr87_gmelt_bg_fixed,pr87_gmelt_bg_process, &
                     pr87_gmelt_alpha*pr87_gmelt_bg_process,pr87_gmelt_bg_after, &
                     pr87_gmelt_q_fixed(3),pr87_gmelt_q_process(3), &
                     pr87_gmelt_alpha*pr87_gmelt_q_process(3),pr87_gmelt_q_after(3), &
                     pr87_gmelt_n_fixed(3),pr87_gmelt_n_process(3), &
                     pr87_gmelt_alpha*pr87_gmelt_n_process(3),pr87_gmelt_n_after(3), &
                     pr87_gmelt_t_fixed,pr87_gmelt_t_process, &
                     pr87_gmelt_alpha*pr87_gmelt_t_process,pr87_gmelt_t_after, &
                     pr87_gmelt_mass_residual,pr87_gmelt_volume_residual, &
                     pr87_gmelt_number_residual,pr87_gmelt_temperature_residual
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger write failed'
                close(pr87_gmelt_unit,iostat=pr87_gmelt_ios)
                if (pr87_gmelt_ios.ne.0) error stop 'PR87 graupel melt ledger close failed'

                if (pr87_gmelt_alpha .gt. 0.0) then
                  qrs(i,k,3)=pr87_gmelt_q_after(5)
                  qrs(i,k,1)=pr87_gmelt_q_after(3)
                  nrs(i,k,1)=pr87_gmelt_n_after(3)
                  brs(i,k)=pr87_gmelt_bg_after
                  t(i,k)=pr87_gmelt_t_after
                endif
              endif
            endif
"""
    if source.count(melt_anchor) != 1:
        raise ValueError("ProgB graupel melt transaction anchor missing or ambiguous")
    source = source.replace(melt_anchor, melt_replacement, 1)

    # ProgB computes its diagnostic density in REAL32.  Reconstructing the
    # prognostic volume from that rounded diagnostic can move a strict-boundary
    # state outside the domain after it has already passed the REAL64 check.
    # Keep the incoming prognostic BG unchanged; rhox remains available for the
    # same physical calculations and output diagnostics.
    progb_rewrite = "          brs(i,k) = qrs(i,k,3)/rhox(i,k)\n"
    if source.count(progb_rewrite) != 1:
        raise ValueError("ProgB REAL32 BG rewrite anchor missing or ambiguous")
    return source.replace(progb_rewrite, "", 1)
