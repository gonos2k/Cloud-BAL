"""Opt in to the density-defined positive ProgB graupel state domain."""

from __future__ import annotations

import hashlib


V42_KDM6_SHA256 = "bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a"
V43_DIAGNOSTIC_KDM6_SHA256 = "9bbf8a8f74badc8d1f30fafa3f330494ebf34bc4c826b02d9935c2f6221341b6"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected one {label} anchor")
    return source.replace(old, new, 1)


def _replace_count(source: str, old: str, new: str, count: int, label: str) -> str:
    if source.count(old) != count:
        raise ValueError(f"expected {count} {label} anchors")
    return source.replace(old, new)


def extend_small_positive_graupel_domain(source: str) -> str:
    """Extend valid QG/BG pairs through all positive REAL32 magnitudes.

    The same finite paired-moment and REAL64 density predicate is used by
    ProgB and the rain-process state validator. The embedded paired
    sedimentation helper keeps its equivalent R32 endpoint predicate.
    """
    actual_hash = hashlib.sha256(source.encode()).hexdigest()
    if actual_hash not in {V42_KDM6_SHA256, V43_DIAGNOSTIC_KDM6_SHA256}:
        raise ValueError(f"unexpected pinned KDM6 source hash: {actual_hash}")

    source = _replace_once(
        source,
        "    private :: pr84_ice_entry_ceiling\n",
        "    private :: pr84_ice_entry_ceiling\n"
        "    private :: kdm6_progb_density_pair_valid\n",
        "density-pair helper visibility",
    )
    pair_helper = """    pure logical function kdm6_progb_density_pair_valid(q,b,rho_min,rho_max)
      real, intent(in) :: q,b,rho_min,rho_max
      real(kind=8) :: density

      kdm6_progb_density_pair_valid=.false.
      if (.not.all(ieee_is_finite([q,b,rho_min,rho_max]))) return
      if (rho_min.le.0.0 .or. rho_max.lt.rho_min) return
      if (q.eq.0.0 .and. b.eq.0.0) then
        kdm6_progb_density_pair_valid=.true.
        return
      endif
      if (q.le.0.0 .or. b.le.0.0) return
      density=real(q,8)/real(b,8)
      kdm6_progb_density_pair_valid=ieee_is_finite(density) .and. &
           density.ge.real(rho_min,8) .and. density.le.real(rho_max,8)
    end function kdm6_progb_density_pair_valid

"""
    source = _replace_once(
        source,
        "    contains\n\n    pure subroutine kdm6_refresh_graupel_intercept(",
        "    contains\n\n" + pair_helper + "    pure subroutine kdm6_refresh_graupel_intercept(",
        "density-pair helper insertion",
    )

    progb_start = source.index("   SUBROUTINE ProgB_param(")
    progb_end = source.index("  END subroutine ProgB_param", progb_start)
    progb = source[progb_start:progb_end]
    progb = _replace_once(
        progb,
        "  real, parameter   :: brs_min = 1.e-15   \n",
        "",
        "ProgB transient volume threshold",
    )
    progb = _replace_once(
        progb,
        "          if (qrs(i,k,3) <= 0.0 .or. brs(i,k) <= 0.0) cycle\n"
        "          if (qrs(i,k,3) <= qcrmin .and. brs(i,k) <= brs_min) then\n"
        "            progb_status(i,k) = PROGB_TRANSIENT\n"
        "            cycle\n"
        "          endif\n"
        "          raw_density = dble(qrs(i,k,3))/dble(brs(i,k))\n"
        "          if (.not. ieee_is_finite(raw_density)) cycle\n"
        "          if (raw_density < dble(rho_min) .or. &\n"
        "              raw_density > dble(rho_max)) cycle\n",
        "          if (.not.kdm6_progb_density_pair_valid(qrs(i,k,3),brs(i,k), &\n"
        "              rho_min,rho_max)) cycle\n"
        "          raw_density = dble(qrs(i,k,3))/dble(brs(i,k))\n",
        "ProgB paired-density gate",
    )
    source = source[:progb_start] + progb + source[progb_end:]

    fraction_start = source.index("    subroutine kdm6_rain_process_fraction(")
    fraction_end = source.index("    end subroutine kdm6_rain_process_fraction", fraction_start)
    fraction = source[fraction_start:fraction_end]
    fraction = _replace_once(
        fraction,
        "            if (qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)) valid_interval=.false.\n",
        "",
        "pair-only small-positive interval rejection",
    )
    fraction = _replace_once(
        fraction,
        "        if (qm(5).gt.0.0d0 .and. bm.gt.0.0d0 .and. &\n"
        "            qm(5).le.real(qcrmin,8) .and. bm.le.real(1.0e-15,8)) &\n"
        "          valid_interval=.false.\n",
        "",
        "full-PSD small-positive interval rejection",
    )
    source = source[:fraction_start] + fraction + source[fraction_end:]

    state_start = source.index("subroutine kdm6_rain_process_state_valid(")
    state_end = source.index("end subroutine kdm6_rain_process_state_valid", state_start)
    state = source[state_start:state_end]
    pair_anchor = """        if (q(5).eq.0.0) then
          if (bg.ne.0.0) then
            if (present(failure_reason)) failure_reason=3
            return
          endif
        else
          if (bg.le.0.0) then
            if (present(failure_reason)) failure_reason=9
            return
          endif
          if (real(q(5),8)/real(bg,8).lt.real(rho_min,8) .or. &
              real(q(5),8)/real(bg,8).gt.real(rho_max,8)) then
            if (present(failure_reason)) failure_reason=9
            return
          endif
          if (q(5).le.qcrmin .and. bg.le.1.0e-15) then
            if (present(failure_reason)) failure_reason=4
            return
          endif
        endif
"""
    pair_replacement = """        if (.not.kdm6_progb_density_pair_valid(q(5),bg,rho_min,rho_max)) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
"""
    state = _replace_once(state, pair_anchor, pair_replacement, "pair-only graupel state gate")
    full_anchor = """      if (q(5).gt.0.0 .or. bg.gt.0.0) then
        if (q(5).le.0.0 .or. bg.le.0.0) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
        if (real(q(5),8)/real(bg,8).lt.real(rho_min,8) .or. &
            real(q(5),8)/real(bg,8).gt.real(rho_max,8)) then
          if (present(failure_reason)) failure_reason=9
          return
        endif
        if (q(5).le.qcrmin .and. bg.le.real(1.0e-15,8)) then
          if (present(failure_reason)) failure_reason=4
          return
        endif
      endif
"""
    state = _replace_once(state, full_anchor, pair_replacement, "full-PSD graupel state gate")
    source = source[:state_start] + state + source[state_end:]

    sediment_start = source.index("SUBROUTINE pr85_kdm6_paired_sediment_column(", source.index("END MODULE module_mp_kdm6"))
    sediment_end = source.index("END SUBROUTINE pr85_kdm6_paired_sediment_column", sediment_start)
    sediment = source[sediment_start:sediment_end]
    sediment = _replace_once(
        sediment,
        "PURE LOGICAL FUNCTION graupel_state_valid(q,b,qmin,bmin,rhomin,rhomax)\n"
        "REAL(real32), INTENT(IN) :: q,b,qmin,bmin,rhomin,rhomax\n",
        "PURE LOGICAL FUNCTION graupel_state_valid(q,b,rhomin,rhomax)\n"
        "REAL(real32), INTENT(IN) :: q,b,rhomin,rhomax\n",
        "sedimentation graupel predicate signature",
    )
    sediment = _replace_once(
        sediment,
        "IF (q<=qmin .AND. b<=bmin) RETURN\n",
        "",
        "sedimentation transient pair rejection",
    )
    sediment = _replace_once(
        sediment,
        "PURE LOGICAL FUNCTION graupel_state_valid(q,b,rhomin,rhomax)\n"
        "REAL(real32), INTENT(IN) :: q,b,rhomin,rhomax\n"
        "REAL(real64) :: density\n"
        "graupel_state_valid=.FALSE.\n"
        "IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(b)) RETURN\n"
        "IF (q<0.0_real32 .OR. b<0.0_real32) RETURN\n"
        "IF (q==0.0_real32 .AND. b==0.0_real32) THEN\n"
        "  graupel_state_valid=.TRUE.; RETURN\n"
        "ENDIF\n"
        "IF (q<=0.0_real32 .OR. b<=0.0_real32) RETURN\n"
        "density=REAL(q,real64)/REAL(b,real64)\n"
        "graupel_state_valid=ieee_is_finite(density) .AND. &\n"
        "  density>=REAL(rhomin,real64) .AND. density<=REAL(rhomax,real64)\n"
        "END FUNCTION graupel_state_valid",
        "PURE LOGICAL FUNCTION graupel_state_valid(q,b,rhomin,rhomax)\n"
        "REAL(real32), INTENT(IN) :: q,b,rhomin,rhomax\n"
        "REAL(real64) :: density\n"
        "graupel_state_valid=.FALSE.\n"
        "IF (.NOT.ieee_is_finite(q) .OR. .NOT.ieee_is_finite(b)) RETURN\n"
        "IF (q<0.0_real32 .OR. b<0.0_real32) RETURN\n"
        "IF (q==0.0_real32 .AND. b==0.0_real32) THEN\n"
        "  graupel_state_valid=.TRUE.; RETURN\n"
        "ENDIF\n"
        "IF (q<=0.0_real32 .OR. b<=0.0_real32) RETURN\n"
        "density=REAL(q,real64)/REAL(b,real64)\n"
        "graupel_state_valid=ieee_is_finite(density) .AND. &\n"
        "  density>=REAL(rhomin,real64) .AND. density<=REAL(rhomax,real64)\n"
        "END FUNCTION graupel_state_valid",
        "duplicate sedimentation density predicate",
    )
    for old, new, label in (
        (
            "graupel_state_valid(qstate(k),second_state(k),q_active_min, &\n"
            "         second_active_min,density_min,density_max)",
            "graupel_state_valid(qstate(k),second_state(k),density_min,density_max)",
            "sedimentation initial state gate",
        ),
        (
            "graupel_state_valid(qr,nr,q_active_min,second_active_min,density_min,density_max)",
            "graupel_state_valid(qr,nr,density_min,density_max)",
            "sedimentation receiver endpoint gate",
        ),
        (
            "graupel_state_valid(qr,nr,q_active_min, &\n"
            "       second_active_min,density_min,density_max)",
            "graupel_state_valid(qr,nr,density_min,density_max)",
            "sedimentation final receiver gate",
        ),
    ):
        sediment = _replace_once(sediment, old, new, label)
    sediment = _replace_count(
        sediment,
        "graupel_state_valid(qd,nd,q_active_min,second_active_min,density_min,density_max)",
        "graupel_state_valid(qd,nd,density_min,density_max)",
        2,
        "sedimentation donor endpoint/final",
    )
    source = source[:sediment_start] + sediment + source[sediment_end:]
    return source
