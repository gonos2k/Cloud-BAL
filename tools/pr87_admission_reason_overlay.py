#!/usr/bin/env python3
"""Add first-failure endpoint reasons to the PR85 v17 AUT/G admission path."""
from __future__ import annotations

import re


def replace_once(text: str, old: str, new: str) -> str:
    count = text.count(old)
    if count != 1:
        raise ValueError(f"expected one source anchor, found {count}: {old[:90]!r}")
    return text.replace(old, new, 1)


def _reason_body(text: str) -> str:
    start = text.index("subroutine kdm6_rain_process_state_valid(")
    end_marker = "end subroutine kdm6_rain_process_state_valid"
    end = text.index(end_marker, start) + len(end_marker)
    prefix, block, suffix = text[:start], text[start:end], text[end:]
    old = """subroutine kdm6_rain_process_state_valid(q,n,bg,temperature,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,valid, &
         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit)"""
    new = """subroutine kdm6_rain_process_state_valid(q,n,bg,temperature,density,pidnr,qmin,ncmin, &
         qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max,pidnc,dmc, &
         lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max,valid, &
         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit,failure_reason)"""
    block = replace_once(block, old, new)
    block = replace_once(block,
        "      real, intent(in), optional :: ice_transient_mass_limit\n      real(kind=8) :: rain_min",
        "      real, intent(in), optional :: ice_transient_mass_limit\n"
        "      integer, intent(out), optional :: failure_reason\n"
        "      real(kind=8) :: rain_min")
    block = replace_once(block,
        "      valid=.false.\n      if (.not.all(ieee_is_finite([q,n,bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr, &",
        "      valid=.false.\n      if (present(failure_reason)) failure_reason=0\n"
        "      if (.not.all(ieee_is_finite([q,n,bg,temperature,density,pidnr,qmin,ncmin,qcrmin,dmr, &")

    substitutions = [
        ("""          lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max]))) return""",
         """          lambda_c_max,pidni,dmi,lambda_i_min,lambda_i_max]))) then
        if (present(failure_reason)) failure_reason=1
        return
      endif"""),
        ("""          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) return""",
         """          dmr.gt.8.0 .or. dmc.gt.8.0 .or. dmi.gt.8.0) then
        if (present(failure_reason)) failure_reason=1
        return
      endif"""),
        ("""            ice_transient_mass_limit.lt.0.0 .or. ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) return""",
         """            ice_transient_mass_limit.lt.0.0 .or. ice_transient_mass_limit.gt.PR85_ICE_NATIVE_INACTIVE_MAX) then
          if (present(failure_reason)) failure_reason=1
          return
        endif"""),
        ("""      if (temperature.le.0.0) return
      if (any(q.lt.0.0) .or. any(n.lt.0.0) .or. bg.lt.0.0) return""",
         """      if (temperature.le.0.0) then
        if (present(failure_reason)) failure_reason=8
        return
      endif
      if (any(q.lt.0.0) .or. any(n.lt.0.0) .or. bg.lt.0.0) then
        if (present(failure_reason)) failure_reason=2
        return
      endif"""),
        ("""          if (n(1).ne.0.0) return""", """          if (n(1).ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif"""),
        ("""        elseif (n(1).le.0.0) then
          return""", """        elseif (n(1).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return"""),
        ("""          if (n(2).ne.0.0) return""", """          if (n(2).ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif"""),
        ("""        elseif (n(2).le.0.0) then
          return""", """        elseif (n(2).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return"""),
        ("""            if (.not.allow_rain_number_at_zero) return""", """            if (.not.allow_rain_number_at_zero) then
              if (present(failure_reason)) failure_reason=3
              return
            endif"""),
        ("""if (.not.present(allow_rain_number_at_zero)) return""", """if (.not.present(allow_rain_number_at_zero)) then
              if (present(failure_reason)) failure_reason=3
              return
            endif"""),
        ("""        if (n(2).ne.0.0) return""", """        if (n(2).ne.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif"""),
        ("""          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) return
            if (.not.allow_rain_number_at_zero) return
          endif""", """          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
            if (.not.allow_rain_number_at_zero) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
          endif"""),
        ("""        elseif (n(3).le.0.0) then
          return""", """        elseif (n(3).le.0.0) then
          if (present(failure_reason)) failure_reason=3
          return"""),
        ("""          if (bg.ne.0.0) return""", """          if (bg.ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif"""),
        ("""          if (bg.le.0.0) return""", """          if (bg.le.0.0) then
            if (present(failure_reason)) failure_reason=9
            return
          endif"""),
        ("""              real(q(5),8)/real(bg,8).gt.real(rho_max,8)) return""", """              real(q(5),8)/real(bg,8).gt.real(rho_max,8)) then
            if (present(failure_reason)) failure_reason=9
            return
          endif"""),
        ("""          if (q(5).le.qcrmin .and. bg.le.1.0e-15) return""", """          if (q(5).le.qcrmin .and. bg.le.1.0e-15) then
            if (present(failure_reason)) failure_reason=4
            return
          endif"""),
        ("""      valid=.true.
      return
      endif
      rain_min=""", """      valid=.true.
      if (present(failure_reason)) failure_reason=0
      return
      endif
      rain_min="""),
        ("""      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) return
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) return""", """      if (.not.all(ieee_is_finite([rain_min,rain_max,cloud_min,cloud_max,ice_min,ice_max]))) then
        if (present(failure_reason)) failure_reason=1
        return
      endif
      if (max(rain_max,cloud_max,ice_max).gt.real(huge(0.0),8)) then
        if (present(failure_reason)) failure_reason=1
        return
      endif"""),
        ("""        if (n(1).ne.0.0) return""", """        if (n(1).ne.0.0) then
          if (present(failure_reason)) failure_reason=3
          return
        endif"""),
        ("""      elseif (q(1).le.0.0 .or. n(1).le.0.0) then
        return
      elseif (real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)) then
        return""", """      elseif (q(1).le.0.0 .or. n(1).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (real(n(1),8).lt.cloud_min*q(1) .or. real(n(1),8).gt.cloud_max*q(1)) then
        if (present(failure_reason)) failure_reason=5
        return"""),
        ("""          if (n(2).ne.0.0) return""", """          if (n(2).ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif"""),
        ("""      elseif (q(2).le.0.0 .or. n(2).le.0.0) then
        return""", """      elseif (q(2).le.0.0 .or. n(2).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return"""),
        ("""        if (real(n(2),8).lt.ice_min*q(2) .or. real(n(2),8).gt.ice_max*q(2)) return""", """        if (real(n(2),8).lt.ice_min*q(2) .or. real(n(2),8).gt.ice_max*q(2)) then
          if (present(failure_reason)) failure_reason=7
          return
        endif"""),
        ("""          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) return
            if (.not.allow_rain_number_at_zero) return
          endif""", """          if (n(3).ne.0.0) then
            if (.not.present(allow_rain_number_at_zero)) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
            if (.not.allow_rain_number_at_zero) then
              if (present(failure_reason)) failure_reason=3
              return
            endif
          endif"""),
        ("""      elseif (q(3).le.0.0 .or. n(3).le.0.0) then
        return
      elseif (real(n(3),8).lt.rain_min*q(3) .or. real(n(3),8).gt.rain_max*q(3)) then
        return""", """      elseif (q(3).le.0.0 .or. n(3).le.0.0) then
        if (present(failure_reason)) failure_reason=3
        return
      elseif (real(n(3),8).lt.rain_min*q(3) .or. real(n(3),8).gt.rain_max*q(3)) then
        if (present(failure_reason)) failure_reason=6
        return"""),
        ("""      if (q(4).lt.0.0 .or. q(5).lt.0.0) return""", """      if (q(4).lt.0.0 .or. q(5).lt.0.0) then
        if (present(failure_reason)) failure_reason=2
        return
      endif"""),
        ("""      if (real(bg,8).lt.real(q(5),8)/real(rho_max,8) .or. &
          real(bg,8).gt.real(q(5),8)/real(rho_min,8)) return
      valid=.true.""", """      if (real(bg,8).lt.real(q(5),8)/real(rho_max,8) .or. &
          real(bg,8).gt.real(q(5),8)/real(rho_min,8)) then
        if (present(failure_reason)) failure_reason=9
        return
      endif
      valid=.true.
      if (present(failure_reason)) failure_reason=0""")
    ]
    for old, new in substitutions:
        if old in block:
            block = block.replace(old, new)

    # The two allow-rain-at-zero sites share most surrounding text, so one may
    # remain after the context-specific substitutions above.
    orphan_guard = re.compile(
        r"(?m)^([ \t]*)if \(\.not\.allow_rain_number_at_zero\) return$"
    )
    block, orphan_count = orphan_guard.subn(
        lambda match: (
            f"{match.group(1)}if (.not.allow_rain_number_at_zero) then\n"
            f"{match.group(1)}  if (present(failure_reason)) failure_reason=3\n"
            f"{match.group(1)}  return\n"
            f"{match.group(1)}endif"
        ),
        block,
    )
    if orphan_count < 1:
        raise ValueError("expected remaining allow-rain guard in validator")

    # Keep this source transform fail-closed if a future validator adds an
    # untagged failure return. The pair-only success return is the sole exempt.
    body_lines = block.splitlines()
    for index, line in enumerate(body_lines):
        stripped = line.strip()
        if "return" not in stripped:
            continue
        if stripped != "return":
            raise ValueError(f"untagged inline validator return: {line!r}")
        prior = body_lines[max(0, index - 3):index]
        if any("valid=.true." in item for item in prior):
            continue
        if not any("failure_reason)" in item for item in prior):
            raise ValueError(f"untagged validator return: {line!r}")
    return prefix + block + suffix


def add_admission_reasons(text: str) -> str:
    """Add optional validator reasons and first-call AUT/G endpoint probes.

    Reason codes: 0 VALID, 1 BADINPUT, 2 DONORNEGATIVE, 3 ORPHAN,
    4 CUTOFF, 5 PSDCLOUD, 6 RAIN, 7 ICE, 8 TEMPERATURE, 9 BULKDENSITY.
    Vapor has separate code 10 when its full-proposal endpoint is negative or
    nonfinite. Reasons describe the validator's first failed endpoint check,
    not the unique constraint that selected the admitted alpha.
    """
    text = _reason_body(text)

    text = replace_once(text,
        "   integer                            :: pr85_cold_unit,pr85_cold_ios",
        "   integer                            :: pr85_cold_unit,pr85_cold_ios\n"
        "   integer                            :: pr87_reason_unit,pr87_reason_ios\n"
        "   integer                            :: pr87_aut_reason,pr87_aut_vapor_reason\n"
        "   integer                            :: pr87_g_reason,pr87_g_vapor_reason\n"
        "   logical                            :: pr87_aut_endpoint_valid,pr87_g_endpoint_valid\n"
        "   real                               :: pr87_endpoint_qv,pr87_mass_specific")

    open_anchor = """   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget header failed'
   open(newunit=pr85_warm_unit"""
    open_add = """   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget header failed'
   if (pr67_trace_this_call) then
     open(newunit=pr87_reason_unit,file='pr87_admission_reason.raw', &
          form='formatted',status='unknown',position='append',action='write', &
          iostat=pr87_reason_ios)
     if (pr87_reason_ios.ne.0) error stop 'PR87 admission reason open failed'
     write(pr87_reason_unit,'(a)',iostat=pr87_reason_ios) &
          '# PR87_ADMISSION group,i,lat,k,loop,status,endpoint_reason,vapor_reason,full_evap_pending,pre_composite_alpha,'// &
          'mass_activity_kg_per_kgdry,rhoDry_kg_m3,DELZ_m; endpoint_reason codes: '// &
          '0 VALID,1 BADINPUT,2 DONORNEGATIVE,3 ORPHAN,4 CUTOFF,5 PSDCLOUD,6 RAIN,7 ICE,'// &
          '8 TEMPERATURE,9 BULKDENSITY; vapor_reason 10=NEGATIVE_OR_NONFINITE_VAPOR; '// &
          'first failed FULL-proposal endpoint check, not a unique active-bound certificate; '// &
          'mass is half-L1 Q+QV proxy'
     if (pr87_reason_ios.ne.0) error stop 'PR87 admission reason header failed'
   endif
   open(newunit=pr85_warm_unit"""
    text = replace_once(text, open_anchor, open_add)

    aut_call = """            call kdm6_rain_process_fraction(rain_q_fixed,rain_aut_q_process, &"""
    aut_probe = """            pr87_aut_reason=0
            pr87_aut_vapor_reason=0
            if (pr67_trace_this_call) then
              call kdm6_rain_process_state_valid( &
                   rain_q_fixed+rain_aut_q_process,rain_n_fixed+rain_aut_n_process, &
                   rain_bg_fixed,rain_t_fixed,dry_carrier_density(i,k),pidnr, &
                   qmin,ncmin,qcrmin,dmr,lamdarmin,lamdarmax,100.0,900.0, &
                   pidnc,dmc,lamdacmin,lamdacmax,pidni,dmi,lamdaimin, &
                   lamdaimax,pr87_aut_endpoint_valid,rain_full_evap_pending(i,k), &
                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                   failure_reason=pr87_aut_reason)
              pr87_endpoint_qv=rain_qv_stage
              if (.not.ieee_is_finite(pr87_endpoint_qv) .or. pr87_endpoint_qv.lt.0.0) &
                   pr87_aut_vapor_reason=10
            endif
            call kdm6_rain_process_fraction(rain_q_fixed,rain_aut_q_process, &"""
    text = replace_once(text, aut_call, aut_probe)

    aut_emit_anchor = """            praut(i,k)=praut(i,k)*rain_aut_alpha"""
    aut_emit = """            if (pr67_trace_this_call .and. rain_aut_alpha.lt.1.0 .and. &
                (any(rain_aut_q_process.ne.0.0) .or. any(rain_aut_n_process.ne.0.0))) then
              pr87_mass_specific=0.5*sum(abs(rain_aut_q_process))
              write(pr87_reason_unit,'(a,1x,a,8(1x,i0),1p,4(1x,es24.16))',iostat=pr87_reason_ios) &
                   'PR87_ADMISSION','AUT',i,lat,k,loop,rain_aut_search_status, &
                   pr87_aut_reason,pr87_aut_vapor_reason, &
                   merge(1,0,rain_full_evap_pending(i,k)),rain_aut_alpha, &
                   pr87_mass_specific,dry_carrier_density(i,k),delz(i,k)
              if (pr87_reason_ios.ne.0) error stop 'PR87 AUT reason write failed'
            endif
            praut(i,k)=praut(i,k)*rain_aut_alpha"""
    text = replace_once(text, aut_emit_anchor, aut_emit)

    g_call = """              call kdm6_rain_process_fraction(rain_q_fixed,rain_g_q_process, &"""
    g_probe = """              pr87_g_reason=0
              pr87_g_vapor_reason=0
              if (pr67_trace_this_call) then
                call kdm6_rain_process_state_valid( &
                     rain_q_fixed+rain_g_q_process,rain_n_fixed+rain_g_n_process, &
                     rain_bg_fixed+rain_g_bg_process,rain_t_fixed+rain_g_t_process, &
                     dry_carrier_density(i,k),pidnr,qmin,ncmin,qcrmin,dmr, &
                     lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &
                     lamdacmax,pidni,dmi,lamdaimin,lamdaimax, &
                     pr87_g_endpoint_valid,rain_full_evap_pending(i,k), &
                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &
                     failure_reason=pr87_g_reason)
                pr87_endpoint_qv=rain_qv_stage+rain_g_qv_process
                if (.not.ieee_is_finite(pr87_endpoint_qv) .or. pr87_endpoint_qv.lt.0.0) &
                     pr87_g_vapor_reason=10
              endif
              call kdm6_rain_process_fraction(rain_q_fixed,rain_g_q_process, &"""
    text = replace_once(text, g_call, g_probe)

    g_emit_anchor = """            if (.not.rain_process_feasible) then
              if (.not.rain_bg_rates_feasible) then"""
    g_emit = """            if (pr67_trace_this_call .and. rain_bg_rates_feasible .and. &
                rain_g_alpha.lt.1.0 .and. &
                (any(rain_g_q_process.ne.0.0) .or. any(rain_g_n_process.ne.0.0) .or. &
                 rain_g_bg_process.ne.0.0 .or. rain_g_t_process.ne.0.0 .or. &
                 rain_g_qv_process.ne.0.0)) then
              pr87_mass_specific=0.5*(sum(abs(rain_g_q_process))+abs(rain_g_qv_process))
              write(pr87_reason_unit,'(a,1x,a,8(1x,i0),1p,4(1x,es24.16))',iostat=pr87_reason_ios) &
                   'PR87_ADMISSION','G',i,lat,k,loop,rain_process_search_status, &
                   pr87_g_reason,pr87_g_vapor_reason, &
                   merge(1,0,rain_full_evap_pending(i,k)),rain_g_alpha, &
                   pr87_mass_specific,dry_carrier_density(i,k),delz(i,k)
              if (pr87_reason_ios.ne.0) error stop 'PR87 G reason write failed'
            endif
            if (.not.rain_process_feasible) then
              if (.not.rain_bg_rates_feasible) then"""
    text = replace_once(text, g_emit_anchor, g_emit)

    close_anchor = """   close(pr85_cold_unit,iostat=pr85_cold_ios)
   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget close failed'
   close(pr85_warm_unit"""
    close_new = """   close(pr85_cold_unit,iostat=pr85_cold_ios)
   if (pr85_cold_ios.ne.0) error stop 'PR85 cold budget close failed'
   if (pr67_trace_this_call) then
     close(pr87_reason_unit,iostat=pr87_reason_ios)
     if (pr87_reason_ios.ne.0) error stop 'PR87 admission reason close failed'
   endif
   close(pr85_warm_unit"""
    text = replace_once(text, close_anchor, close_new)
    return text
