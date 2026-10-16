"""Add a read-only, one-cell graupel horizontal-diffusion probe to V24c."""

from __future__ import annotations

import hashlib


V24C_EM_SHA256 = "bf97496a1013b86ac0382fb9dfb22ad9e818af996d5bcb49bebcbdeec790f8b2"
V39_EM_SHA256 = "e48607da8943caaf86f53c5fc04ff5ba2a2c75e32706142c97c3f9b8fdb70c70"
V39_NATIVE_UPDATE_SHA256 = "d997a6393552465132ee7a743d59f5f37214e6521781dae928c44d6621001503"
_DIFFUSION_CALL = """CALL horizontal_diffusion ( 'm', scalar(ims,kms,jms,im),            &
                                            scalar_tends(ims,kms,jms,im), mut, &
                                            c1h, c2h, config_flags,            &
                                            msfux, msfuy, msfvx, msfvx_inv,    &
                                            msfvy, msftx, msfty,               &
                                            khdq , xkmhd, rdx, rdy,            &
                                            ids, ide, jds, jde, kds, kde,      &
                                            ims, ime, jms, jme, kms, kme,      &
                                            its, ite, jts, jte, kts, kte      )"""
_QIB_USE_ANCHOR = "p_qnr, p_qnc, tiedtkescheme"
_V39_DIFFUSION_CALL = """CALL horizontal_diffusion ( 'm', scalar(ims,kms,jms,im),            &
                                            scalar_tends(ims,kms,jms,im), mut, &
                                            c1h, c2h, config_flags,            &
                                            msfux, msfuy, msfvx, msfvx_inv,    &
                                            msfvy, msftx, msfty,               &
                                            khdq , xkmhd, rdx, rdy,            &
                                            ids, ide, jds, jde, kds, kde,      &
                                            ims, ime, jms, jme, kms, kme,      &
                                            its, ite, jts, jte, kts, kte      )"""
_V39_NATIVE_FULL_ANCHOR = """          WRITE(u,*) 'FULL',itimestep,rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &
              qb(cell,p),nb(cell,p),qs64(cell,p),ns64(cell,p),qa64(cell,p),na64(cell,p), &
              source_candidate,full_stored,drydensity(cell),dt"""


def _v39_diffusion_probe(phase: str) -> str:
    return f"""           IF (rk_step == 1 .AND. config_flags%mp_physics == 37 .AND. &
               config_flags%diff_opt == 1 .AND. .NOT. mix2_off .AND. &
               ((moist_step .AND. im == P_QG) .OR. &
                (.NOT. moist_step .AND. im == P_QIB)) .AND. &
               154 >= its .AND. 154 <= ite .AND. 77 >= jts .AND. 77 <= jte .AND. &
               17 >= kts .AND. 17 <= kte .AND. 154 > ims .AND. 155 < ime .AND. &
               77 > jms .AND. 78 < jme) THEN
             WRITE(*,'(A,1X,5(I0,1X),2(L1,1X),*(1X,ES25.17E3))') &
                 'PR87_G39_DIFFUSION_{phase}', rk_step, im, 154, 77, 17, &
                 moist_step, mix2_off, dt_step, khdq, &
                 scalar_tends(154,17,77,im), scalar(154,17,77,im), &
                 scalar(153,17,77,im), scalar(155,17,77,im), &
                 scalar(154,17,76,im), scalar(154,17,78,im), &
                 mut(154,77), mut(153,77), mut(155,77), mut(154,76), mut(154,78), &
                 c1h(17), c2h(17), &
                 xkmhd(154,17,77), xkmhd(153,17,77), xkmhd(155,17,77), &
                 xkmhd(154,17,76), xkmhd(154,17,78), &
                 msfux(153,77), msfux(154,77), msfux(155,77), &
                 msfuy(153,77), msfuy(154,77), msfuy(155,77), &
                 msfvx_inv(154,77), msfvx_inv(154,78), &
                 msfvy(154,77), msfvy(154,78), &
                 msftx(154,77), msfty(154,77), rdx, rdy
           END IF
"""


def _v39_diffusion_result_probe() -> str:
    return """                 IF (rk_step == 1 .AND. moist_step .AND. im == P_QG .AND. &
                     pr87_diff_i == 154 .AND. pr87_diff_j == 77 .AND. pr87_diff_k == 17 .AND. &
                     154 >= pr87_diff_i_start .AND. 154 <= pr87_diff_i_end .AND. &
                     77 >= pr87_diff_j_start .AND. 77 <= pr87_diff_j_end .AND. &
                     17 >= kts .AND. 17 <= pr87_diff_k_end) THEN
                   WRITE(*,'(A,1X,5(I0,1X),1P,8ES26.17)') &
                       'PR87_G39_DIFFUSION_RESULT', rk_step, im, 154, 77, 17, &
                       dt_step, pr87_rain_tendency_before(154,17,77), &
                       scalar_tends(154,17,77,im), &
                       pr87_rain_diffusion_increment(154,17,77), &
                       all_pair_diffusion_delta(154,17,77,pr87_diff_channel), &
                       REAL(pr87_rain_tendency_before(154,17,77),real64) + &
                           pr87_rain_diffusion_increment(154,17,77)
                 END IF
                 IF (rk_step == 1 .AND. .NOT. moist_step .AND. im == P_QIB .AND. &
                     pr87_diff_i == 154 .AND. pr87_diff_j == 77 .AND. pr87_diff_k == 17 .AND. &
                     154 >= pr87_diff_i_start .AND. 154 <= pr87_diff_i_end .AND. &
                     77 >= pr87_diff_j_start .AND. 77 <= pr87_diff_j_end .AND. &
                     17 >= kts .AND. 17 <= pr87_diff_k_end) THEN
                   WRITE(*,'(A,1X,5(I0,1X),1P,8ES26.17)') &
                       'PR87_G39_DIFFUSION_RESULT', rk_step, im, 154, 77, 17, &
                       dt_step, pr87_rain_tendency_before(154,17,77), &
                       scalar_tends(154,17,77,im), &
                       pr87_rain_diffusion_increment(154,17,77), &
                       all_pair_diffusion_delta(154,17,77,pr87_diff_channel), &
                       REAL(pr87_rain_tendency_before(154,17,77),real64) + &
                           pr87_rain_diffusion_increment(154,17,77)
                 END IF
"""


def extend_v39_graupel_diffusion_probe(em: str) -> str:
    """Add read-only QG/QIB stencil and R64 correction records at the V39 failure cell."""
    actual = hashlib.sha256(em.encode("utf-8")).hexdigest()
    if actual != V39_EM_SHA256:
        raise ValueError(f"unexpected V39 module_em source: {actual}")
    if em.count(_V39_DIFFUSION_CALL) != 1:
        raise ValueError("expected exactly one pinned V39 horizontal_diffusion call")
    if em.count("all_pair_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &") != 1:
        raise ValueError("expected exactly one V39 all-pair diffusion correction assignment")

    result = em.replace(_V39_DIFFUSION_CALL,
                        _v39_diffusion_probe("PRE") + _V39_DIFFUSION_CALL +
                        "\n" + _v39_diffusion_probe("POST"), 1)
    assignment = """                 all_pair_diffusion_delta(pr87_diff_i,pr87_diff_k,pr87_diff_j, &
                                      pr87_diff_channel) = &
                      REAL(pr87_rain_tendency_before(pr87_diff_i,pr87_diff_k,pr87_diff_j),real64) + &
                      pr87_rain_diffusion_increment(pr87_diff_i,pr87_diff_k,pr87_diff_j) - &
                      REAL(scalar_tends(pr87_diff_i,pr87_diff_k,pr87_diff_j,im),real64)"""
    if result.count(assignment) != 1:
        raise ValueError("V39 diffusion correction expression changed")
    result = result.replace(assignment, assignment + "\n" + _v39_diffusion_result_probe(), 1)
    expected_counts = {"PRE": 1, "POST": 1, "RESULT": 2}
    for tag, count in expected_counts.items():
        if result.count(f"'PR87_G39_DIFFUSION_{tag}'") != count:
            raise ValueError(f"expected {count} V39 diffusion {tag} records")
    if result.count(_V39_DIFFUSION_CALL) != 1:
        raise ValueError("V39 horizontal_diffusion call was changed")
    return result


def extend_v39_full_source_components(native_update: str) -> str:
    """Add a failure-only component row for p4 source and diffusion rates."""
    actual = hashlib.sha256(native_update.encode("utf-8")).hexdigest()
    if actual != V39_NATIVE_UPDATE_SHA256:
        raise ValueError(f"unexpected V39 native update fragment: {actual}")
    if native_update.count(_V39_NATIVE_FULL_ANCHOR) != 1:
        raise ValueError("expected exactly one pinned V39 FULL failure write")
    replacement = _V39_NATIVE_FULL_ANCHOR + """
          IF (p==4 .AND. PRESENT(pr87_all_pair_diffusion_delta)) THEN
            WRITE(u,'(a,6i10,1p,14es26.17)') 'FULL_SOURCE_COMPONENTS',itimestep,rk,p,i,j,k, &
                REAL(qs(cell,p),real64),REAL(ns(cell,p),real64), &
                pr87_all_pair_diffusion_delta(i,k,j,7),pr87_all_pair_diffusion_delta(i,k,j,8), &
                qs64(cell,p),ns64(cell,p),qa64(cell,p),na64(cell,p), &
                REAL(oldcarrier(cell),real64),REAL(newcarrier(cell),real64), &
                REAL(dt,real64),REAL(drydensity(cell),real64),source_candidate
          END IF"""
    result = native_update.replace(_V39_NATIVE_FULL_ANCHOR, replacement, 1)
    if result.count("'FULL_SOURCE_COMPONENTS'") != 1:
        raise ValueError("expected exactly one failure-only source-components record")
    if result.count("WRITE(u,*) 'FULL'") != 1:
        raise ValueError("FULL failure record changed")
    return result


def _probe(phase: str) -> str:
    return f"""           IF (rk_step == 1 .AND. config_flags%mp_physics == 37 .AND. &
               config_flags%diff_opt == 1 .AND. &
               ((moist_step .AND. im == P_QG) .OR. &
                (.NOT. moist_step .AND. im == P_QIB)) .AND. &
               8 >= its .AND. 8 <= ite .AND. 205 >= jts .AND. 205 <= jte .AND. &
               16 >= kts .AND. 16 <= kte .AND. 8 > ims .AND. 9 < ime .AND. &
               205 > jms .AND. 206 < jme) THEN
             WRITE(*,'(A,1X,5(I0,1X),2(L1,1X),*(1X,ES25.17E3))') &
                 'PR87_G_DIFFUSION_{phase}', rk_step, im, 8, 205, 16, &
                 moist_step, mix2_off, dt_step, khdq, &
                 scalar_tends(8,16,205,im), scalar(8,16,205,im), &
                 scalar(7,16,205,im), scalar(9,16,205,im), &
                 scalar(8,16,204,im), scalar(8,16,206,im), &
                 mut(8,205), mut(7,205), mut(9,205), mut(8,204), mut(8,206), &
                 c1h(16), c2h(16), &
                 xkmhd(8,16,205), xkmhd(7,16,205), xkmhd(9,16,205), &
                 xkmhd(8,16,204), xkmhd(8,16,206), &
                 msfux(7,205), msfux(8,205), msfux(9,205), &
                 msfuy(7,205), msfuy(8,205), msfuy(9,205), &
                 msfvx_inv(8,205), msfvx_inv(8,206), &
                 msfvy(8,205), msfvy(8,206), &
                 msftx(8,205), msfty(8,205), rdx, rdy
           END IF
"""


def extend_graupel_diffusion_probe(em: str) -> str:
    """Insert PRE/POST G-Q and G-B diffusion records; leave the call untouched."""
    actual = hashlib.sha256(em.encode("utf-8")).hexdigest()
    if actual != V24C_EM_SHA256:
        raise ValueError(f"unexpected V24c module_em source: {actual}")
    if em.count(_DIFFUSION_CALL) != 1:
        raise ValueError("expected exactly one pinned horizontal_diffusion call")
    if em.count(_QIB_USE_ANCHOR) != 1:
        raise ValueError("expected exactly one pinned state-description import anchor")

    result = em.replace(_QIB_USE_ANCHOR, "p_qnr, p_qnc, p_qib, tiedtkescheme", 1)
    result = result.replace(_DIFFUSION_CALL, _probe("PRE") + _DIFFUSION_CALL + "\n" + _probe("POST"), 1)
    if result.count(_DIFFUSION_CALL) != 1:
        raise ValueError("horizontal_diffusion call changed during probe insertion")
    if result.count("p_qnc, p_qib, tiedtkescheme") != 1:
        raise ValueError("P_QIB state-description import was not added exactly once")
    if result.count("'PR87_G_DIFFUSION_PRE'") != 1 or result.count("'PR87_G_DIFFUSION_POST'") != 1:
        raise ValueError("probe insertion did not produce one PRE and one POST record")
    return result
