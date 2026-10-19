"""Generate the pinned V21 pending-ice-sublimation overlay."""
from __future__ import annotations

import hashlib
import re


V21_MODULE_SOURCE_SHA256 = "8679f2e7c51940ab740bbe9e768dbb68156e9c655f459245f522f7983fb99eb9"
V39_FINAL_MODULE_SOURCE_SHA256 = "6a7f6e154390ad6d5da8ca18ea4115ad66effa5b1dbdbf73754edd357b6b4293"
V39_CAP_ORDER_SOURCE_SHA256 = "faa81931252f6f28cc74ca3367a5c721668fe9ca0f01225641fb495a93ca6959"


def _sha256_text(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _replace_all(source: str, old: str, new: str, expected: int, label: str) -> str:
    count = source.count(old)
    if count != expected:
        raise ValueError(f"expected {expected} {label} anchors, found {count}")
    return source.replace(old, new)


def extend_ice_sublimation_pending(source: str) -> str:
    """Add a pending marker for exact full ice sublimation.

    The marker is visible only to the cold NG/AUT/G admission searches. The
    committed REAL32 endpoint remains paired: number is cleared only when the
    stored ice mass is exactly zero.
    """
    if _sha256_text(source) != V21_MODULE_SOURCE_SHA256:
        raise ValueError("KDM6 source does not match the pinned V21 preimage")

    # Extend the helper APIs with optional trailing arguments so existing
    # callers, including the separate warm search, retain their old behavior.
    source = _replace_once(
        source,
        "         ice_transient_mass_limit)\n",
        "         ice_transient_mass_limit,ice_sublimation_pending)\n",
        "fraction optional argument list",
    )
    old_fraction_option = "      real, intent(in), optional :: ice_transient_mass_limit\n"
    if source.count(old_fraction_option) != 2:
        raise ValueError("expected the two pinned transient-limit declarations")
    source = source.replace(
        old_fraction_option,
        old_fraction_option +
        "      logical, intent(in), optional :: ice_sublimation_pending\n",
        1,
    )
    source = _replace_once(
        source,
        "      logical :: pair_only\n\n      feasible=.false.\n",
        "      logical :: pair_only,ice_sublimation_pending_value\n\n      feasible=.false.\n",
        "fraction local declaration",
    )
    old_pair_default = (
        "      pair_only=.false.\n"
        "      if (present(consumer_pair_only)) pair_only=consumer_pair_only\n"
    )
    if source.count(old_pair_default) != 2:
        raise ValueError("expected the pinned fraction and validator pair defaults")
    source = source.replace(
        old_pair_default,
        old_pair_default +
        "      ice_sublimation_pending_value=.false.\n"
        "      if (present(ice_sublimation_pending)) &\n"
        "        ice_sublimation_pending_value=ice_sublimation_pending\n",
        1,
    )
    source = _replace_once(
        source,
        "             qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max, &\n"
        "             pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &\n"
        "             lambda_i_max,is_valid,rain_cleanup_pending,pair_only,ice_transient_mass_limit)\n",
        "             qmin,ncmin,qcrmin,dmr,lambda_min,lambda_max,rho_min,rho_max, &\n"
        "             pidnc,dmc,lambda_c_min,lambda_c_max,pidni,dmi,lambda_i_min, &\n"
        "             lambda_i_max,is_valid,rain_cleanup_pending,pair_only, &\n"
        "             ice_transient_mass_limit, &\n"
        "             ice_sublimation_pending=ice_sublimation_pending_value)\n",
        "trial validator forwarding",
    )

    source = _replace_once(
        source,
        "         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit,failure_reason)\n",
        "         allow_rain_number_at_zero,consumer_pair_only,ice_transient_mass_limit, &\n"
        "         failure_reason,ice_sublimation_pending)\n",
        "state validator optional argument list",
    )
    source = _replace_once(
        source,
        "      integer, intent(out), optional :: failure_reason\n",
        "      integer, intent(out), optional :: failure_reason\n"
        "      logical, intent(in), optional :: ice_sublimation_pending\n",
        "state validator optional declaration",
    )
    source = _replace_once(
        source,
        "      logical :: pair_only\n\n      valid=.false.\n",
        "      logical :: pair_only,ice_pending\n\n      valid=.false.\n",
        "state validator local declaration",
    )
    source = _replace_once(
        source,
        "      pair_only=.false.\n      if (present(consumer_pair_only)) pair_only=consumer_pair_only\n      if (pair_only) then\n",
        "      pair_only=.false.\n"
        "      if (present(consumer_pair_only)) pair_only=consumer_pair_only\n"
        "      ice_pending=.false.\n"
        "      if (present(ice_sublimation_pending)) ice_pending=ice_sublimation_pending\n"
        "      if (pair_only) then\n",
        "state validator pending default",
    )

    # Exact zero ice mass with positive number is permitted only during a
    # marked cold search. Negative moments and positive-mass orphan states
    # remain rejected by the existing checks.
    source = _replace_once(
        source,
        "        if (q(2).eq.0.0) then\n"
        "          if (n(2).ne.0.0) then\n"
        "            if (present(failure_reason)) failure_reason=3\n"
        "            return\n"
        "          endif\n"
        "        elseif (n(2).le.0.0) then\n",
        "        if (q(2).eq.0.0) then\n"
        "          if (n(2).ne.0.0 .and. .not.ice_pending) then\n"
        "            if (present(failure_reason)) failure_reason=3\n"
        "            return\n"
        "          endif\n"
        "        elseif (n(2).le.0.0) then\n",
        "pair-only ice state predicate",
    )
    source = _replace_once(
        source,
        "      if (q(2).eq.0.0) then\n"
        "        if (n(2).ne.0.0) then\n"
        "          if (present(failure_reason)) failure_reason=3\n"
        "          return\n"
        "        endif\n"
        "      elseif (q(2).le.0.0 .or. n(2).le.0.0) then\n",
        "      if (q(2).eq.0.0) then\n"
        "        if (n(2).ne.0.0 .and. .not.ice_pending) then\n"
        "          if (present(failure_reason)) failure_reason=3\n"
        "          return\n"
        "        endif\n"
        "      elseif (q(2).le.0.0 .or. n(2).le.0.0) then\n",
        "strict ice state predicate",
    )

    # Keep the exact zero-mass endpoint available to the scalar search without
    # clipping positive number. Other orphan states stay infeasible.
    source = _replace_once(
        source,
        "            elseif (m.eq.3 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &\n"
        "                    rain_cleanup_pending) then\n",
        "            elseif (m.eq.2 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &\n"
        "                    ice_sublimation_pending_value) then\n"
        "              call clip(q0(m),dq(m),lo,hi,valid_interval)\n"
        "              call clip(-q0(m),-dq(m),lo,hi,valid_interval)\n"
        "            elseif (m.eq.3 .and. qm(m).eq.0.0d0 .and. nm(m).gt.0.0d0 .and. &\n"
        "                    rain_cleanup_pending) then\n",
        "pair-only pending ice interval",
    )
    source = _replace_once(
        source,
        "        elseif (qm(2).eq.0.0d0 .and. nm(2).eq.0.0d0) then\n"
        "          call clip(q0(2),dq(2),lo,hi,valid_interval)\n",
        "        elseif (qm(2).eq.0.0d0 .and. nm(2).gt.0.0d0 .and. &\n"
        "                ice_sublimation_pending_value) then\n"
        "          call clip(q0(2),dq(2),lo,hi,valid_interval)\n"
        "          call clip(-q0(2),-dq(2),lo,hi,valid_interval)\n"
        "        elseif (qm(2).eq.0.0d0 .and. nm(2).eq.0.0d0) then\n"
        "          call clip(q0(2),dq(2),lo,hi,valid_interval)\n",
        "strict pending ice interval",
    )

    # Allocate the marker and event details per cell and reset with the
    # existing rain pending flag.
    source = _replace_once(
        source,
        "   logical, dimension(its:ite,kts:kte) :: rain_full_evap_pending\n",
        "   logical, dimension(its:ite,kts:kte) :: rain_full_evap_pending\n"
        "   logical, dimension(its:ite,kts:kte) :: ice_full_sublimation_pending\n"
        "   real, dimension(its:ite,kts:kte) :: ice_sublimation_raw_pidep\n"
        "   real, dimension(its:ite,kts:kte) :: ice_sublimation_capped_pidep\n"
        "   real, dimension(its:ite,kts:kte) :: ice_sublimation_q_before,ice_sublimation_n_before\n"
        "   integer, dimension(its:ite,kts:kte) :: ice_sublimation_event_count\n",
        "per-cell pending state declarations",
    )
    source = _replace_once(
        source,
        "          rain_full_evap_pending(i,k) = .false.\n",
        "          rain_full_evap_pending(i,k) = .false.\n"
        "          ice_full_sublimation_pending(i,k) = .false.\n"
        "          ice_sublimation_raw_pidep(i,k) = 0.0\n"
        "          ice_sublimation_capped_pidep(i,k) = 0.0\n"
        "          ice_sublimation_q_before(i,k) = 0.0\n"
        "          ice_sublimation_n_before(i,k) = 0.0\n"
        "          ice_sublimation_event_count(i,k) = 0\n",
        "per-cell pending initialization",
    )
    source = _replace_once(
        source,
        "              if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 nci(i,k,2) = 0.\n"
        "              endif\n",
        "              if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 ice_full_sublimation_pending(i,k) = .true.\n"
        "                 ice_sublimation_raw_pidep(i,k) = pidep(i,k)\n"
        "                 ice_sublimation_q_before(i,k) = qci(i,k,2)\n"
        "                 ice_sublimation_n_before(i,k) = nci(i,k,2)\n"
        "                 ice_sublimation_event_count(i,k) = &\n"
        "                      ice_sublimation_event_count(i,k) + 1\n"
        "              endif\n",
        "early full-sublimation number reset",
    )
    source = _replace_once(
        source,
        "              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)).ge.abs(satdt)) ifsat = 1\n",
        "              if (ice_full_sublimation_pending(i,k)) &\n"
        "                ice_sublimation_capped_pidep(i,k) = pidep(i,k)\n"
        "              if(abs(prevp(i,k)+pinud(i,k)+pidep(i,k)).ge.abs(satdt)) ifsat = 1\n",
        "capped sublimation rate capture",
    )

    # Thread the pending marker only through the cold NG/AUT/G searches and
    # their pretrial state checks. Warm calls intentionally remain unchanged.
    source = _replace_once(
        source,
        "                 rain_ng_feasible,rain_ng_search_status,rain_qv_before,rain_ng_qv_process, &\n"
        "                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)\n",
        "                 rain_ng_feasible,rain_ng_search_status,rain_qv_before,rain_ng_qv_process, &\n"
        "                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                 ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "NG fraction pending argument",
    )
    source = _replace_once(
        source,
        "                     lamdaimax,rain_ng_base_valid,rain_full_evap_pending(i,k), &\n"
        "                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)\n",
        "                     lamdaimax,rain_ng_base_valid,rain_full_evap_pending(i,k), &\n"
        "                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                     ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "NG base validator pending argument",
    )
    # AUT: endpoint, fraction and infeasible-base validation.
    source = _replace_once(
        source,
        "                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                   failure_reason=pr87_aut_reason)\n",
        "                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                   failure_reason=pr87_aut_reason, &\n"
        "                   ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "AUT endpoint pending argument",
    )
    source = _replace_once(
        source,
        "                 rain_aut_feasible,rain_aut_search_status,rain_qv_stage,0.0, &\n"
        "                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)\n",
        "                 rain_aut_feasible,rain_aut_search_status,rain_qv_stage,0.0, &\n"
        "                 ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                 ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "AUT fraction pending argument",
    )
    source = _replace_once(
        source,
        "                     lamdaimax,rain_aut_base_valid,rain_full_evap_pending(i,k), &\n"
        "                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)\n",
        "                     lamdaimax,rain_aut_base_valid,rain_full_evap_pending(i,k), &\n"
        "                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                     ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "AUT base validator pending argument",
    )
    # G: endpoint, fraction and deferred-base validation.
    source = _replace_once(
        source,
        "                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                     failure_reason=pr87_g_reason)\n",
        "                     ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                     failure_reason=pr87_g_reason, &\n"
        "                     ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "G endpoint pending argument",
    )
    source = _replace_once(
        source,
        "                   rain_qv_stage,rain_g_qv_process,ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)\n",
        "                   rain_qv_stage,rain_g_qv_process, &\n"
        "                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                   ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n",
        "G fraction pending argument",
    )
    source = _replace_once(
        source,
        "                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX)\n"
        "              if (rain_aut_base_valid .and. ieee_is_finite(rain_qv_stage) .and. &\n",
        "                   ice_transient_mass_limit=PR85_ICE_NATIVE_INACTIVE_MAX, &\n"
        "                   ice_sublimation_pending=ice_full_sublimation_pending(i,k))\n"
        "              if (rain_aut_base_valid .and. ieee_is_finite(rain_qv_stage) .and. &\n",
        "G deferred-base pending argument",
    )

    # On each stored composite retry, clear ice number only if the actual
    # REAL32 ice mass is exactly zero. The following stored validator remains
    # strict and does not receive the pending marker.
    source = _replace_once(
        source,
        "            if (rain_full_evap_pending(i,k) .and. rain_q_after(3).eq.0.0) then\n",
        "            pr87_ice_sublimation_extinctions=0\n"
        "            pr87_ice_sublimation_n_preclear=rain_n_after(2)\n"
        "            pr87_ice_sublimation_dn=0.0\n"
        "            if (ice_full_sublimation_pending(i,k) .and. rain_q_after(2).eq.0.0) then\n"
        "              if (rain_n_after(2).gt.0.0) then\n"
        "                pr87_ice_sublimation_extinctions=1\n"
        "                pr87_ice_sublimation_dn=-rain_n_after(2)\n"
        "              endif\n"
        "              rain_n_after(2)=0.0\n"
        "            endif\n"
        "            if (rain_full_evap_pending(i,k) .and. rain_q_after(3).eq.0.0) then\n",
        "stored full-sublimation endpoint handling",
    )
    source = _replace_once(
        source,
        "   integer :: rain_composite_retry,rain_composite_rate_index\n",
        "   integer :: rain_composite_retry,rain_composite_rate_index\n"
        "   integer :: pr87_ice_sublimation_extinctions,pr87_ice_sublimation_unit\n"
        "   integer :: pr87_ice_sublimation_ios\n"
        "   real :: pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn\n",
        "sublimation ledger declarations",
    )

    # The sparse ledger records committed events and never labels a partial
    # Q decrease as number extinction.
    source = _replace_once(
        source,
        "              error stop 'KDM6 rejected an invalid stored process endpoint'\n"
        "            endif\n"
        "            ! Existing full v17 ledgers remain the reference.\n",
        "              error stop 'KDM6 rejected an invalid stored process endpoint'\n"
        "            endif\n"
        "            if (ice_full_sublimation_pending(i,k)) then\n"
        "              open(newunit=pr87_ice_sublimation_unit, &\n"
        "                   file='pr87_ice_sublimation_pending.raw',form='formatted', &\n"
        "                   status='unknown',position='append',action='write', &\n"
        "                   iostat=pr87_ice_sublimation_ios)\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-sublimation ledger open failed'\n"
        "              write(pr87_ice_sublimation_unit,'(a)',iostat=pr87_ice_sublimation_ios) &\n"
        "                   '# PR87_ICE_SUBLIMATION step,i,lat,k,loop,n_sed,events,'// &\n"
        "                   'raw_pidep[kg/kg/s],capped_pidep[kg/kg/s],Qbefore[kg/kg],Nbefore[m-3],'// &\n"
        "                   'Qafter[kg/kg],Nafter[m-3],Ncandidate_preclear[m-3],dN_extinction[m-3],'// &\n"
        "                   'alphaNG,alphaAUT,alphaG,gammaComposite,retry,extinctions'\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-sublimation ledger header failed'\n"
        "              write(pr87_ice_sublimation_unit,'(a,7i9,1p,12e24.16,0p,2i9)', &\n"
        "                   iostat=pr87_ice_sublimation_ios) 'PR87_ICE_SUBLIMATION', &\n"
        "                   pr87_model_timestep,i,lat,k,loop,n, &\n"
        "                   ice_sublimation_event_count(i,k), &\n"
        "                   ice_sublimation_raw_pidep(i,k),ice_sublimation_capped_pidep(i,k), &\n"
        "                   ice_sublimation_q_before(i,k),ice_sublimation_n_before(i,k), &\n"
        "                   rain_q_after(2),rain_n_after(2), &\n"
        "                   pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn, &\n"
        "                   rain_ng_alpha,rain_aut_alpha, &\n"
        "                   rain_g_alpha,rain_composite_gamma,rain_composite_retry, &\n"
        "                   pr87_ice_sublimation_extinctions\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-sublimation ledger write failed'\n"
        "              close(pr87_ice_sublimation_unit,iostat=pr87_ice_sublimation_ios)\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-sublimation ledger close failed'\n"
        "              ice_full_sublimation_pending(i,k)=.false.\n"
        "              ice_sublimation_event_count(i,k)=0\n"
        "            endif\n",
        "sublimation sparse ledger",
    )

    return source


def correct_ice_sublimation_cap_order(source: str) -> str:
    """Mark exact full sublimation only after the native rate caps approve it."""
    actual = _sha256_text(source)
    if actual != V39_FINAL_MODULE_SOURCE_SHA256:
        raise ValueError(f"KDM6 source does not match the pinned V39 final preimage: {actual}")

    declaration = (
        "   integer, dimension(its:ite,kts:kte) :: ice_sublimation_event_count\n"
    )
    if source.count(declaration) != 1:
        raise ValueError("expected one V39 ice-sublimation event-count declaration")
    source = source.replace(
        declaration,
        declaration + "   real :: pr87_ice_raw_pidep_before_caps\n",
        1,
    )

    raw_and_caps = (
        "              if(pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                 ice_full_sublimation_pending(i,k) = .true.\n"
        "                 ice_sublimation_raw_pidep(i,k) = pidep(i,k)\n"
        "                 ice_sublimation_q_before(i,k) = qci(i,k,2)\n"
        "                 ice_sublimation_n_before(i,k) = nci(i,k,2)\n"
        "                 ice_sublimation_event_count(i,k) = &\n"
        "                      ice_sublimation_event_count(i,k) + 1\n"
        "              endif\n"
        "                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)\n"
        "                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)\n"
    )
    capped_test = (
        "                pr87_ice_raw_pidep_before_caps=pidep(i,k)\n"
        "                pidep(i,k) = max(pidep(i,k),-(qci(i,k,2))/dtcld)\n"
        "                pidep(i,k) = max(max(pidep(i,k),(satdt)/2),supice)\n"
        "                if (pidep(i,k).eq.-(qci(i,k,2))/dtcld) then\n"
        "                  ice_full_sublimation_pending(i,k) = .true.\n"
        "                  ice_sublimation_raw_pidep(i,k) = pr87_ice_raw_pidep_before_caps\n"
        "                  ice_sublimation_q_before(i,k) = qci(i,k,2)\n"
        "                  ice_sublimation_n_before(i,k) = nci(i,k,2)\n"
        "                  ice_sublimation_event_count(i,k) = &\n"
        "                       ice_sublimation_event_count(i,k) + 1\n"
        "                  ice_sublimation_capped_pidep(i,k) = pidep(i,k)\n"
        "                endif\n"
    )
    if source.count(raw_and_caps) != 1:
        raise ValueError("expected one V39 raw full-sublimation predicate and cap pair")
    source = source.replace(raw_and_caps, capped_test, 1)

    stale_capped_write = (
        "              if (ice_full_sublimation_pending(i,k)) &\n"
        "                ice_sublimation_capped_pidep(i,k) = pidep(i,k)\n"
    )
    if source.count(stale_capped_write) != 1:
        raise ValueError("expected one V39 post-cap pending-rate ledger write")
    source = source.replace(stale_capped_write, "", 1)

    if source.count("pr87_ice_raw_pidep_before_caps=pidep(i,k)") != 1:
        raise ValueError("raw pidep capture must occur exactly once before the caps")
    if source.count("ice_sublimation_capped_pidep(i,k) = pidep(i,k)") != 1:
        raise ValueError("capped pidep ledger must be written only with approved full removal")
    return source


def complete_cold_ice_extinction(source: str) -> str:
    """Allow paired cold-process endpoints that exhaust cloud ice exactly.

    Existing full-sublimation cap handling remains in the input. This adds the
    same pending endpoint only when an NG or G proposal can consume all current
    ice mass at one shared process fraction.
    """
    source = correct_ice_sublimation_cap_order(source)
    actual = _sha256_text(source)
    if actual != V39_CAP_ORDER_SOURCE_SHA256:
        raise ValueError(f"cap-corrected KDM6 source pin mismatch: {actual}")

    source = _replace_once(
        source,
        "   logical, dimension(its:ite,kts:kte) :: ice_full_sublimation_pending\n",
        "   logical, dimension(its:ite,kts:kte) :: ice_full_sublimation_pending\n"
        "   integer, dimension(its:ite,kts:kte) :: ice_extinction_cause\n",
        "cold ice extinction cause declaration",
    )
    old_ice_clear = (
        "            pr87_ice_sublimation_extinctions=0\n"
        "            pr87_ice_sublimation_n_preclear=rain_n_after(2)\n"
        "            pr87_ice_sublimation_dn=0.0\n"
        "            if (ice_full_sublimation_pending(i,k) .and. rain_q_after(2).eq.0.0) then\n"
        "              if (rain_n_after(2).gt.0.0) then\n"
        "                pr87_ice_sublimation_extinctions=1\n"
        "                pr87_ice_sublimation_dn=-rain_n_after(2)\n"
        "              endif\n"
        "              rain_n_after(2)=0.0\n"
        "            endif\n"
    )
    guarded_ice_clear = (
        "            pr87_ice_sublimation_extinctions=0\n"
        "            pr87_ice_sublimation_n_preclear=rain_n_after(2)\n"
        "            pr87_ice_sublimation_dn=0.0\n"
        "            if (rain_composite_valid) then\n"
        "              if (ieee_is_finite(rain_n_after(2))) then\n"
        "                if (rain_n_after(2).ge.0.0) then\n"
        "                  if (ice_full_sublimation_pending(i,k) .and. &\n"
        "                      rain_q_after(2).eq.0.0) then\n"
        "                    if (rain_n_after(2).gt.0.0) then\n"
        "                      pr87_ice_sublimation_extinctions=1\n"
        "                      pr87_ice_sublimation_dn=-rain_n_after(2)\n"
        "                    endif\n"
        "                    rain_n_after(2)=0.0\n"
        "                  endif\n"
        "                endif\n"
        "              endif\n"
        "            endif\n"
    )
    source = _replace_once(source, old_ice_clear, guarded_ice_clear, "valid exact-zero ice clear")
    source = _replace_once(
        source,
        "          ice_full_sublimation_pending(i,k) = .false.\n",
        "          ice_full_sublimation_pending(i,k) = .false.\n"
        "          ice_extinction_cause(i,k) = 0\n",
        "cold ice extinction cause initialization",
    )
    source = _replace_once(
        source,
        "                  ice_full_sublimation_pending(i,k) = .true.\n",
        "                  ice_full_sublimation_pending(i,k) = .true.\n"
        "                  ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),1)\n",
        "PIDEp extinction cause bit",
    )

    ng_exhaustion = (
        "            if (ieee_is_finite(rain_q_before(2))) then\n"
        "              if (rain_q_before(2).gt.0.0) then\n"
        "                if (ieee_is_finite(rain_ng_q_process(2))) then\n"
        "                  if (rain_ng_q_process(2).lt.0.0) then\n"
        "                    if (rain_ng_q_process(2).le.-rain_q_before(2)) then\n"
        "                      ice_full_sublimation_pending(i,k)=.true.\n"
        "                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),2)\n"
        "                    endif\n"
        "                  endif\n"
        "                endif\n"
        "              endif\n"
        "            endif\n"
    )
    source = _replace_once(
        source,
        "            rain_ng_q_process(5)=0.0\n",
        "            rain_ng_q_process(5)=0.0\n" + ng_exhaustion,
        "NG aggregate ice-exhaustion eligibility",
    )

    g_exhaustion = (
        "            if (ieee_is_finite(rain_q_fixed(2))) then\n"
        "              if (rain_q_fixed(2).gt.0.0) then\n"
        "                if (ieee_is_finite(rain_g_q_process(2))) then\n"
        "                  if (rain_g_q_process(2).lt.0.0) then\n"
        "                    if (rain_g_q_process(2).le.-rain_q_fixed(2)) then\n"
        "                      ice_full_sublimation_pending(i,k)=.true.\n"
        "                      ice_extinction_cause(i,k)=ior(ice_extinction_cause(i,k),4)\n"
        "                    endif\n"
        "                  endif\n"
        "                endif\n"
        "              endif\n"
        "            endif\n"
    )
    source = _replace_once(
        source,
        "            rain_ng_aut_q_fixed=rain_q_fixed\n",
        g_exhaustion + "            rain_ng_aut_q_fixed=rain_q_fixed\n",
        "G aggregate ice-exhaustion eligibility",
    )

    # Keep the original sublimation ledger for pure full-PIDEp events. Any
    # process-driven authorization gets its own cause-coded record.
    source = _replace_once(
        source,
        "            if (ice_full_sublimation_pending(i,k)) then\n"
        "              open(newunit=pr87_ice_sublimation_unit, &\n",
        "            if (ice_full_sublimation_pending(i,k) .and. ice_extinction_cause(i,k).le.1) then\n"
        "              open(newunit=pr87_ice_sublimation_unit, &\n",
        "pure sublimation ledger guard",
    )
    aggregate_ledger = (
        "            if (ice_full_sublimation_pending(i,k) .and. ice_extinction_cause(i,k).gt.1) then\n"
        "              open(newunit=pr87_ice_sublimation_unit, &\n"
        "                   file='pr87_ice_extinction.raw',form='formatted', &\n"
        "                   status='unknown',position='append',action='write', &\n"
        "                   iostat=pr87_ice_sublimation_ios)\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-extinction ledger open failed'\n"
        "              write(pr87_ice_sublimation_unit,'(a)',iostat=pr87_ice_sublimation_ios) &\n"
        "                   '# PR87_ICE_EXTINCTION step,i,lat,k,loop,n_sed,cause_bits,'// &\n"
        "                   'Qbefore[kg/kg],Nbefore[m-3],Qafter[kg/kg],Nafter[m-3],'// &\n"
        "                   'Npreclear[m-3],dN[m-3],raw_pidep[kg/kg/s],capped_pidep[kg/kg/s],'// &\n"
        "                   'alphaNG,alphaAUT,alphaG,gammaComposite,retry,extinctions'\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-extinction ledger header failed'\n"
        "              write(pr87_ice_sublimation_unit,'(a,7i9,1p,12e24.16,0p,2i9)', &\n"
        "                   iostat=pr87_ice_sublimation_ios) 'PR87_ICE_EXTINCTION', &\n"
        "                   pr87_model_timestep,i,lat,k,loop,n,ice_extinction_cause(i,k), &\n"
        "                   rain_q_before(2),rain_n_before(2),rain_q_after(2),rain_n_after(2), &\n"
        "                   pr87_ice_sublimation_n_preclear,pr87_ice_sublimation_dn, &\n"
        "                   ice_sublimation_raw_pidep(i,k),ice_sublimation_capped_pidep(i,k), &\n"
        "                   rain_ng_alpha,rain_aut_alpha,rain_g_alpha,rain_composite_gamma, &\n"
        "                   rain_composite_retry,pr87_ice_sublimation_extinctions\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-extinction ledger write failed'\n"
        "              close(pr87_ice_sublimation_unit,iostat=pr87_ice_sublimation_ios)\n"
        "              if (pr87_ice_sublimation_ios.ne.0) &\n"
        "                error stop 'PR87 ice-extinction ledger close failed'\n"
        "            endif\n"
    )
    source = _replace_once(
        source,
        "            enddo\n            factor=rain_g_alpha\n",
        "            enddo\n" + aggregate_ledger + "            factor=rain_g_alpha\n",
        "pre-commit aggregate ice-extinction ledger",
    )
    source = _replace_once(
        source,
        "            endif\n            if (.false.) then\n            write(pr85_cold_unit,",
        "            endif\n"
        "            if (ice_full_sublimation_pending(i,k) .and. ice_extinction_cause(i,k).gt.1) then\n"
        "              ice_full_sublimation_pending(i,k)=.false.\n"
        "              ice_extinction_cause(i,k)=0\n"
        "              ice_sublimation_event_count(i,k)=0\n"
        "            endif\n"
        "            if (.false.) then\n            write(pr85_cold_unit,",
        "post-validation aggregate extinction reset",
    )
    return source

