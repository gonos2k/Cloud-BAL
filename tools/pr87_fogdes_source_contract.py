"""Fold the explicit Shinhong cloud source correction into paired FogDES.

The opt-in path validates the full REAL64 cloud endpoint including the PBL
source sidecar. It stores tendencies in REAL32 and replaces the sidecar by the
residual needed for the native source consumer to recover that endpoint.
"""
from __future__ import annotations

import hashlib

FOGDES_SHA256 = "6e3efe52abc669e51a01175ceaeba48e91b92d13f57b700a2cf8359a0e23b361"
DRIVER_SHA256 = {
    "v26c": "106674d12edc3c66b42b1148db40949a1dbe43c2d1ccf98bb6876403c8fccc85",
    "v26c_compact": "0f15fdbe7a3d1fdb07e7ba06dfcf1749e93d0aa4403876974158d3abd7b53458",
}


def _sha(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise ValueError(f"expected one {label} anchor, found {count}")
    return source.replace(old, new, 1)


def _extend_fogdes(source: str) -> str:
    source = _replace_once(
        source,
        "MODULE module_bl_fogdes\n\n  USE module_model_constants\n",
        "MODULE module_bl_fogdes\n\n  USE module_model_constants\n"
        "  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64\n",
        "FogDES module imports",
    )
    source = _replace_once(
        source,
        "ground_q_sink,ground_n_sink)\n"
        "    INTEGER,INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme\n",
        "ground_q_sink,ground_n_sink,cloud_source_delta64,source_step)\n"
        "    INTEGER,INTENT(IN) :: ids,ide,jds,jde,kds,kde,ims,ime,jms,jme,kms,kme\n",
        "FogDES QN entry signature",
    )
    source = _replace_once(
        source,
        "    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)\n"
        "    REAL :: grav_scale\n",
        "    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)\n"
        "    REAL(real64),INTENT(INOUT),OPTIONAL :: cloud_source_delta64(ims:ime,kms:kme,jms:jme,2)\n"
        "    INTEGER,INTENT(IN),OPTIONAL :: source_step\n"
        "    REAL :: grav_scale\n",
        "FogDES QN entry declarations",
    )
    source = _replace_once(
        source,
        "    CALL fogdes_qn_stokes_flux(vdfg,qc_curr,qnc_curr,qv_curr,t_curr,dtbl,grav_scale,rho,dz8w,dqc,dqnc, &\n"
        "         ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte)\n",
        "    IF (PRESENT(cloud_source_delta64)) THEN\n"
        "      CALL fogdes_qn_stokes_flux(vdfg,qc_curr,qnc_curr,qv_curr,t_curr,dtbl,grav_scale,rho,dz8w,dqc,dqnc, &\n"
        "           ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte, &\n"
        "           cloud_source_delta64,source_step)\n"
        "    ELSE\n"
        "      CALL fogdes_qn_stokes_flux(vdfg,qc_curr,qnc_curr,qv_curr,t_curr,dtbl,grav_scale,rho,dz8w,dqc,dqnc, &\n"
        "           ground_q_sink,ground_n_sink,ims,ime,jms,jme,kms,kme,kde,its,ite,jts,jte,kts,kte)\n"
        "    ENDIF\n",
        "FogDES QN inner call",
    )

    source = _replace_once(
        source,
        "       its,ite,jts,jte,kts,kte)\n"
        "    USE, INTRINSIC :: iso_fortran_env, ONLY: real64\n",
        "       its,ite,jts,jte,kts,kte,cloud_source_delta64,source_step)\n"
        "    USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64\n",
        "FogDES flux signature",
    )
    source = _replace_once(
        source,
        "    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)\n"
        "    REAL(real64),PARAMETER :: mu_shape=2.0_real64\n",
        "    REAL,INTENT(OUT) :: ground_q_sink(ims:ime,jms:jme),ground_n_sink(ims:ime,jms:jme)\n"
        "    REAL(real64),INTENT(INOUT),OPTIONAL :: cloud_source_delta64(ims:ime,kms:kme,jms:jme,2)\n"
        "    INTEGER,INTENT(IN),OPTIONAL :: source_step\n"
        "    REAL(real64),PARAMETER :: mu_shape=2.0_real64\n",
        "FogDES flux payload declarations",
    )
    source = _replace_once(
        source,
        "    REAL(real64),PARAMETER :: mmax=3.0300855069345996e-10_real64\n"
        "    REAL(real64),PARAMETER :: alpha=mu_shape+1.0_real64\n",
        "    REAL(real64),PARAMETER :: mmax=3.0300855069345996e-10_real64\n"
        "    REAL(real64),PARAMETER :: cloud_pidn=REAL(523.59881591796875_real32,real64)\n"
        "    REAL(real64),PARAMETER :: cloud_lambda_min=12000.0_real64,cloud_lambda_max=500000.0_real64\n"
        "    REAL(real64),PARAMETER :: strict_mmin=cloud_pidn/cloud_lambda_max**3.0_real64\n"
        "    REAL(real64),PARAMETER :: strict_mmax=cloud_pidn/cloud_lambda_min**3.0_real64\n"
        "    REAL(real64),PARAMETER :: alpha=mu_shape+1.0_real64\n",
        "FogDES strict cloud bounds",
    )
    source = _replace_once(
        source,
        "    REAL(real64) :: base_dq(kms:kte),base_dn(kms:kte)\n"
        "    REAL(real64) :: theta,lo,hi\n",
        "    REAL(real64) :: base_dq(kms:kte),base_dn(kms:kte)\n"
        "    REAL(real64) :: corrected_base_dq(kms:kte),corrected_base_dn(kms:kte)\n"
        "    REAL(real64) :: input_delta_q(kms:kte),input_delta_n(kms:kte)\n"
        "    REAL(real64) :: total_rate_q(kms:kte),total_rate_n(kms:kte)\n"
        "    REAL(real64) :: legacy_rate_q(kms:kte),legacy_rate_n(kms:kte)\n"
        "    REAL(real64) :: output_delta_q(kms:kte),output_delta_n(kms:kte)\n"
        "    REAL :: stored_rate_q(kms:kte),stored_rate_n(kms:kte)\n"
        "    REAL(real64) :: theta,lo,hi,rate_q64,rate_n64,reconstructed_q64,reconstructed_n64\n"
        "    REAL(real32) :: theta32\n",
        "FogDES correction scratch",
    )
    source = _replace_once(
        source,
        "    INTEGER :: i,j,k,ktop,iteration,budget_unit,io_status\n"
        "    LOGICAL :: feasible\n",
        "    REAL(real64) :: incoming_sum_q,incoming_sum_n,incoming_l1_q,incoming_l1_n\n"
        "    REAL(real64) :: outgoing_sum_q,outgoing_sum_n,outgoing_l1_q,outgoing_l1_n\n"
        "    REAL(real64) :: incoming_max_q,incoming_max_n,outgoing_max_q,outgoing_max_n\n"
        "    REAL(real64) :: sample_in_q,sample_in_n,sample_out_q,sample_out_n\n"
        "    INTEGER :: i,j,k,ktop,iteration,budget_unit,io_status,changed_count,sample_k\n"
        "    LOGICAL :: feasible\n",
        "FogDES local declarations",
    )
    source = _replace_once(
        source,
        "    IF (.NOT.ieee_is_finite(dt) .OR. dt<=0.0) &\n"
        "      CALL wrf_error_fatal('FogDES paired Stokes settling requires positive timestep')\n",
        "    IF (PRESENT(cloud_source_delta64)) THEN\n"
        "      IF (.NOT.PRESENT(source_step)) &\n"
        "        CALL wrf_error_fatal('FogDES source correction requires an explicit timestep')\n"
        "      IF (source_step<1) CALL wrf_error_fatal('FogDES source correction has invalid timestep')\n"
        "    ENDIF\n"
        "    IF (.NOT.ieee_is_finite(dt) .OR. dt<=0.0) &\n"
        "      CALL wrf_error_fatal('FogDES paired Stokes settling requires positive timestep')\n",
        "FogDES timestep check",
    )
    source = _replace_once(
        source,
        "      'PR85_FOGDES_BUDGET_UNITS local_rho_dry_times_dz Q_kg_per_m2 N_per_m2 residual=committed_plus_ground'\n"
        "    IF (ktop<kts) THEN\n",
        "      'PR85_FOGDES_BUDGET_UNITS local_rho_dry_times_dz Q_kg_per_m2 N_per_m2 residual=committed_plus_ground'\n"
        "    WRITE(budget_unit,'(a)') &\n"
        "      'PR87_FOGDES_SOURCE_CORRECTION_UNITS Q/N are unweighted tendency-rate deltas per dry-air mass per second; summaries are not budgets'\n"
        "    IF (ktop<kts) THEN\n",
        "FogDES source correction units header",
    )
    source = _replace_once(
        source,
        "          base_dq(k)=REAL(dqc(i,k,j),real64)\n"
        "          base_dn(k)=REAL(dqnc(i,k,j),real64)\n",
        "          base_dq(k)=REAL(dqc(i,k,j),real64)\n"
        "          base_dn(k)=REAL(dqnc(i,k,j),real64)\n"
        "          corrected_base_dq(k)=base_dq(k)\n"
        "          corrected_base_dn(k)=base_dn(k)\n"
        "          input_delta_q(k)=0.0_real64; input_delta_n(k)=0.0_real64\n"
        "          IF (PRESENT(cloud_source_delta64)) THEN\n"
        "            input_delta_q(k)=cloud_source_delta64(i,k,j,1)\n"
        "            input_delta_n(k)=cloud_source_delta64(i,k,j,2)\n"
        "            IF (.NOT.ALL(ieee_is_finite([input_delta_q(k),input_delta_n(k)]))) &\n"
        "              CALL wrf_error_fatal('FogDES source correction is nonfinite')\n"
        "            corrected_base_dq(k)=base_dq(k)+input_delta_q(k)\n"
        "            corrected_base_dn(k)=base_dn(k)+input_delta_n(k)\n"
        "            IF (.NOT.ALL(ieee_is_finite([corrected_base_dq(k),corrected_base_dn(k)]))) &\n"
        "              CALL wrf_error_fatal('FogDES corrected base tendency is nonfinite')\n"
        "          ENDIF\n",
        "FogDES corrected tendency base",
    )
    old_candidate = """        stored_dq=REAL(base_dq(kk)+scale*dq(kk))
        stored_dn=REAL(base_dn(kk)+scale*dn(kk))
        IF (.NOT.ieee_is_finite(stored_dq) .OR. .NOT.ieee_is_finite(stored_dn)) RETURN
        qstate32=qc(i,kk,j)+dt*stored_dq
        nstate32=qnc(i,kk,j)+dt*stored_dn
        qvalue=REAL(qstate32,real64)
        nvalue=REAL(nstate32,real64)
"""
    new_candidate = """        IF (PRESENT(cloud_source_delta64)) THEN
          rate_q64=corrected_base_dq(kk)+scale*dq(kk)
          rate_n64=corrected_base_dn(kk)+scale*dn(kk)
          legacy_rate_q(kk)=base_dq(kk)+scale*dq(kk)
          legacy_rate_n(kk)=base_dn(kk)+scale*dn(kk)
          IF (.NOT.ALL(ieee_is_finite([rate_q64,rate_n64,legacy_rate_q(kk),legacy_rate_n(kk)]))) RETURN
          IF (ABS(rate_q64)>REAL(HUGE(0.0_real32),real64) .OR. &
              ABS(rate_n64)>REAL(HUGE(0.0_real32),real64) .OR. &
              ABS(legacy_rate_q(kk))>REAL(HUGE(0.0_real32),real64) .OR. &
              ABS(legacy_rate_n(kk))>REAL(HUGE(0.0_real32),real64)) RETURN
          stored_dq=REAL(legacy_rate_q(kk),real32)
          stored_dn=REAL(legacy_rate_n(kk),real32)
          IF (.NOT.ieee_is_finite(stored_dq) .OR. .NOT.ieee_is_finite(stored_dn)) RETURN
          output_delta_q(kk)=rate_q64-REAL(stored_dq,real64)
          output_delta_n(kk)=rate_n64-REAL(stored_dn,real64)
          reconstructed_q64=REAL(stored_dq,real64)+output_delta_q(kk)
          reconstructed_n64=REAL(stored_dn,real64)+output_delta_n(kk)
          IF (.NOT.ALL(ieee_is_finite([output_delta_q(kk),output_delta_n(kk), &
                                      reconstructed_q64,reconstructed_n64]))) RETURN
          qvalue=REAL(qc(i,kk,j),real64)+REAL(dt,real64)*reconstructed_q64
          nvalue=REAL(qnc(i,kk,j),real64)+REAL(dt,real64)*reconstructed_n64
        ELSE
          stored_dq=REAL(base_dq(kk)+scale*dq(kk))
          stored_dn=REAL(base_dn(kk)+scale*dn(kk))
          IF (.NOT.ieee_is_finite(stored_dq) .OR. .NOT.ieee_is_finite(stored_dn)) RETURN
          qstate32=qc(i,kk,j)+dt*stored_dq
          nstate32=qnc(i,kk,j)+dt*stored_dn
          qvalue=REAL(qstate32,real64)
          nvalue=REAL(nstate32,real64)
        ENDIF
"""
    source = _replace_once(source, old_candidate, new_candidate, "FogDES candidate source endpoint")
    source = _replace_once(
        source,
        "          theta=lo\n        ENDIF\n        CALL candidate(theta,feasible)\n",
        "          theta=lo\n        ENDIF\n"
        "        IF (PRESENT(cloud_source_delta64) .AND. theta>0.0_real64 .AND. theta<1.0_real64) THEN\n"
        "          theta32=REAL(theta,real32)\n"
        "          IF (REAL(theta32,real64)>theta) theta32=NEAREST(theta32,-1.0_real32)\n"
        "          theta=REAL(theta32,real64)\n"
        "        ENDIF\n"
        "        CALL candidate(theta,feasible)\n",
        "FogDES representable theta selection",
    )
    source = _replace_once(
        source,
        "        lower_tol=8.0_real64*REAL(SPACING(REAL(mmin)),real64)\n"
        "        upper_tol=8.0_real64*REAL(SPACING(REAL(mmax)),real64)\n"
        "        IF (meanmass<mmin-lower_tol .OR. meanmass>mmax+upper_tol) RETURN\n",
        "        IF (PRESENT(cloud_source_delta64)) THEN\n"
        "          IF (qvalue<strict_mmin*nvalue .OR. qvalue>strict_mmax*nvalue) RETURN\n"
        "        ELSE\n"
        "          lower_tol=8.0_real64*REAL(SPACING(REAL(mmin)),real64)\n"
        "          upper_tol=8.0_real64*REAL(SPACING(REAL(mmax)),real64)\n"
        "          IF (meanmass<mmin-lower_tol .OR. meanmass>mmax+upper_tol) RETURN\n"
        "        ENDIF\n",
        "FogDES exact opt-in endpoint check",
    )
    old_commit = """        DO k=kts,ktop
          dqc(i,k,j)=REAL(base_dq(k)+theta*dq(k))
          dqnc(i,k,j)=REAL(base_dn(k)+theta*dn(k))
          dryrho=REAL(rho(i,k,j)/(1.0+qv(i,k,j)),real64)
"""
    new_commit = """        IF (PRESENT(cloud_source_delta64)) THEN
          incoming_sum_q=0.0_real64; incoming_sum_n=0.0_real64
          incoming_l1_q=0.0_real64; incoming_l1_n=0.0_real64
          outgoing_sum_q=0.0_real64; outgoing_sum_n=0.0_real64
          outgoing_l1_q=0.0_real64; outgoing_l1_n=0.0_real64
          incoming_max_q=0.0_real64; incoming_max_n=0.0_real64
          outgoing_max_q=0.0_real64; outgoing_max_n=0.0_real64
          changed_count=0; sample_k=0
          sample_in_q=0.0_real64; sample_in_n=0.0_real64
          sample_out_q=0.0_real64; sample_out_n=0.0_real64
          DO k=kts,ktop
            total_rate_q(k)=corrected_base_dq(k)+theta*dq(k)
            total_rate_n(k)=corrected_base_dn(k)+theta*dn(k)
            legacy_rate_q(k)=base_dq(k)+theta*dq(k)
            legacy_rate_n(k)=base_dn(k)+theta*dn(k)
            IF (.NOT.ALL(ieee_is_finite([total_rate_q(k),total_rate_n(k), &
                                        legacy_rate_q(k),legacy_rate_n(k)]))) &
              CALL wrf_error_fatal('FogDES accepted source correction is nonfinite')
            IF (ABS(total_rate_q(k))>REAL(HUGE(0.0_real32),real64) .OR. &
                ABS(total_rate_n(k))>REAL(HUGE(0.0_real32),real64) .OR. &
                ABS(legacy_rate_q(k))>REAL(HUGE(0.0_real32),real64) .OR. &
                ABS(legacy_rate_n(k))>REAL(HUGE(0.0_real32),real64)) &
              CALL wrf_error_fatal('FogDES accepted tendency exceeds REAL32 range')
            stored_rate_q(k)=REAL(legacy_rate_q(k),real32)
            stored_rate_n(k)=REAL(legacy_rate_n(k),real32)
            output_delta_q(k)=total_rate_q(k)-REAL(stored_rate_q(k),real64)
            output_delta_n(k)=total_rate_n(k)-REAL(stored_rate_n(k),real64)
            IF (.NOT.ALL(ieee_is_finite([output_delta_q(k),output_delta_n(k)]))) &
              CALL wrf_error_fatal('FogDES accepted source correction is nonfinite')
            IF (input_delta_q(k)/=0.0_real64 .OR. input_delta_n(k)/=0.0_real64 .OR. &
                output_delta_q(k)/=0.0_real64 .OR. output_delta_n(k)/=0.0_real64) THEN
              changed_count=changed_count+1
              incoming_sum_q=incoming_sum_q+input_delta_q(k)
              incoming_sum_n=incoming_sum_n+input_delta_n(k)
              incoming_l1_q=incoming_l1_q+ABS(input_delta_q(k))
              incoming_l1_n=incoming_l1_n+ABS(input_delta_n(k))
              incoming_max_q=MAX(incoming_max_q,ABS(input_delta_q(k)))
              incoming_max_n=MAX(incoming_max_n,ABS(input_delta_n(k)))
              outgoing_sum_q=outgoing_sum_q+output_delta_q(k)
              outgoing_sum_n=outgoing_sum_n+output_delta_n(k)
              outgoing_l1_q=outgoing_l1_q+ABS(output_delta_q(k))
              outgoing_l1_n=outgoing_l1_n+ABS(output_delta_n(k))
              outgoing_max_q=MAX(outgoing_max_q,ABS(output_delta_q(k)))
              outgoing_max_n=MAX(outgoing_max_n,ABS(output_delta_n(k)))
              IF (sample_k==0) THEN
                sample_k=k
                sample_in_q=input_delta_q(k); sample_in_n=input_delta_n(k)
                sample_out_q=output_delta_q(k); sample_out_n=output_delta_n(k)
              ENDIF
            ENDIF
          ENDDO
          IF (changed_count>0) THEN
            WRITE(budget_unit,'(a,5i10,1p,17es24.16)',IOSTAT=io_status) &
              'PR87_FOGDES_SOURCE_CORRECTION_RK',source_step,i,j,changed_count,sample_k,theta, &
              incoming_sum_q,incoming_sum_n,incoming_l1_q,incoming_l1_n, &
              incoming_max_q,incoming_max_n,outgoing_sum_q,outgoing_sum_n, &
              outgoing_l1_q,outgoing_l1_n,outgoing_max_q,outgoing_max_n, &
              sample_in_q,sample_in_n,sample_out_q,sample_out_n
            IF (io_status/=0) CALL wrf_error_fatal('FogDES source correction ledger write failed')
          ENDIF
          DO k=kts,ktop
            dqc(i,k,j)=stored_rate_q(k)
            dqnc(i,k,j)=stored_rate_n(k)
            cloud_source_delta64(i,k,j,1)=output_delta_q(k)
            cloud_source_delta64(i,k,j,2)=output_delta_n(k)
          ENDDO
        ELSE
          DO k=kts,ktop
            dqc(i,k,j)=REAL(base_dq(k)+theta*dq(k))
            dqnc(i,k,j)=REAL(base_dn(k)+theta*dn(k))
          ENDDO
        ENDIF
        DO k=kts,ktop
          dryrho=REAL(rho(i,k,j)/(1.0+qv(i,k,j)),real64)
"""
    source = _replace_once(source, old_commit, new_commit, "FogDES corrected tendency commit")

    return source


def extend_fogdes_source_contract(fogdes_source: str, pbl_driver_source: str) -> dict[str, str]:
    """Transform the V26c FogDES source and pre/post-compact PBL driver."""
    fog_hash = _sha(fogdes_source)
    driver_hash = _sha(pbl_driver_source)
    if fog_hash != FOGDES_SHA256:
        raise ValueError(f"FogDES source SHA-256 mismatch: {fog_hash}")
    if driver_hash not in DRIVER_SHA256.values():
        raise ValueError(f"PBL driver source SHA-256 mismatch: {driver_hash}")
    return {"fogdes": _extend_fogdes(fogdes_source),
            "pbl_driver": _extend_driver(pbl_driver_source)}


def _extend_driver(source: str) -> str:
    if _sha(source) == DRIVER_SHA256["v26c"]:
        if source.count("              ,pr87_tendency_delta64 &\n!\n! END FASDAS") != 1:
            raise ValueError("V26c driver signature anchor missing")
    elif _sha(source) == DRIVER_SHA256["v26c_compact"]:
        if source.count("              ,pr87_compact_diagnostics &\n!\n! END FASDAS") != 1:
            raise ValueError("compact driver signature anchor missing")
    else:
        raise ValueError("PBL driver source identity changed during transform")
    call_old = ("                    ground_n_sink=fogdes_ground_n_sink)\n")
    call_new = ("                    ground_n_sink=fogdes_ground_n_sink,                         &\n"
                "                    cloud_source_delta64=pr87_tendency_delta64(:,:,:,1:2),      &\n"
                "                    source_step=itimestep)\n")
    source = _replace_once(source, call_old, call_new, "PBL driver FogDES call")
    return source
