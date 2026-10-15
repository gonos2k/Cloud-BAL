SUBROUTINE pr85_kdm6_rain_freezing_packet(qrain,nrain,qgraupel,vgraupel, &
dry_density,mass_requested,number_requested,volume_requested, &
rain_min,rain_max,graupel_density_min,graupel_density_max, &
qrain_after,nrain_after,qgraupel_after,vgraupel_after, &
mass_approved,number_approved,volume_approved,fraction,base_valid,accepted)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL(real32), INTENT(IN) :: qrain,nrain,qgraupel,vgraupel,dry_density
REAL(real64), INTENT(IN) :: mass_requested,number_requested,volume_requested
REAL(real64), INTENT(IN) :: rain_min,rain_max,graupel_density_min,graupel_density_max
REAL(real32), INTENT(OUT) :: qrain_after,nrain_after,qgraupel_after,vgraupel_after
REAL(real64), INTENT(OUT) :: mass_approved,number_approved,volume_approved,fraction
LOGICAL, INTENT(OUT) :: base_valid,accepted
REAL(real64) :: theta
REAL(real32) :: qrt,nrt,qgt,vgt
LOGICAL :: feasible,found
INTEGER :: attempt

qrain_after=qrain; nrain_after=nrain
qgraupel_after=qgraupel; vgraupel_after=vgraupel
mass_approved=0.0_real64; number_approved=0.0_real64
volume_approved=0.0_real64; fraction=0.0_real64
base_valid=.FALSE.; accepted=.FALSE.
IF (.NOT.ALL(ieee_is_finite([qrain,nrain,qgraupel,vgraupel,dry_density]))) RETURN
IF (.NOT.ALL(ieee_is_finite([mass_requested,number_requested,volume_requested, &
    rain_min,rain_max,graupel_density_min,graupel_density_max]))) RETURN
IF (MIN(qrain,nrain,qgraupel,vgraupel)<0.0_real32 .OR. dry_density<=0.0_real32) RETURN
IF (MIN(mass_requested,number_requested,volume_requested)<0.0_real64) RETURN
IF (rain_min<=0.0_real64 .OR. rain_max<rain_min .OR. &
    graupel_density_min<=0.0_real64 .OR. graupel_density_max<graupel_density_min) RETURN
IF (MIN(rain_min,graupel_density_min)<REAL(TINY(0.0_real32),real64) .OR. &
    MAX(rain_max,graupel_density_max)>REAL(HUGE(0.0_real32),real64)) RETURN
IF (.NOT.paired(qrain,nrain) .OR. .NOT.paired(qgraupel,vgraupel)) RETURN
IF (.NOT.rain_cone(qrain,nrain,dry_density,rain_min,rain_max) .OR. &
    .NOT.graupel_cone(qgraupel,vgraupel,graupel_density_min,graupel_density_max)) RETURN
base_valid=.TRUE.
IF (mass_requested==0.0_real64 .AND. number_requested==0.0_real64 .AND. &
    volume_requested==0.0_real64) THEN
  accepted=.TRUE.
  RETURN
ENDIF
! This source process is one coupled mass/number/volume packet. A missing
! moment proposal cannot be repaired with a floor or a post-process remap.
IF (mass_requested<=0.0_real64 .OR. number_requested<=0.0_real64 .OR. &
    volume_requested<=0.0_real64) RETURN

theta=1.0_real64
found=.FALSE.
DO attempt=0,48
  CALL candidate(theta,qrt,nrt,qgt,vgt,feasible)
  IF (feasible) THEN
    found=.TRUE.
    EXIT
  ENDIF
  theta=theta*0.5_real64
ENDDO
IF (.NOT.found) RETURN
qrain_after=qrt; nrain_after=nrt
qgraupel_after=qgt; vgraupel_after=vgt
fraction=theta
mass_approved=theta*mass_requested
number_approved=theta*number_requested
volume_approved=theta*volume_requested
accepted=.TRUE.

CONTAINS

SUBROUTINE candidate(scale,qro,nro,qgo,vgo,ok)
REAL(real64), INTENT(IN) :: scale
REAL(real32), INTENT(OUT) :: qro,nro,qgo,vgo
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: qr64,nr64,qg64,vg64,r32max
qro=qrain; nro=nrain; qgo=qgraupel; vgo=vgraupel
ok=.FALSE.
r32max=REAL(HUGE(0.0_real32),real64)
qr64=REAL(qrain,real64)-scale*mass_requested
nr64=REAL(nrain,real64)-scale*number_requested
qg64=REAL(qgraupel,real64)+scale*mass_requested
vg64=REAL(vgraupel,real64)+scale*volume_requested
IF (.NOT.ALL(ieee_is_finite([qr64,nr64,qg64,vg64]))) RETURN
IF (MIN(qr64,nr64,qg64,vg64)<0.0_real64 .OR. &
    MAX(qr64,nr64,qg64,vg64)>r32max) RETURN
qro=REAL(qr64,real32); nro=REAL(nr64,real32)
qgo=REAL(qg64,real32); vgo=REAL(vg64,real32)
IF (.NOT.ALL(ieee_is_finite([qro,nro,qgo,vgo]))) RETURN
IF (.NOT.paired(qro,nro) .OR. .NOT.paired(qgo,vgo)) RETURN
! Do not approve a transfer unless all four source/receiver changes are stored.
IF (qro>=qrain .OR. nro>=nrain .OR. qgo<=qgraupel .OR. vgo<=vgraupel) RETURN
IF (.NOT.change_matches(REAL(qrain,real64)-REAL(qro,real64), &
    scale*mass_requested,qro)) RETURN
IF (.NOT.change_matches(REAL(nrain,real64)-REAL(nro,real64), &
    scale*number_requested,nro)) RETURN
IF (.NOT.change_matches(REAL(qgo,real64)-REAL(qgraupel,real64), &
    scale*mass_requested,qgo)) RETURN
IF (.NOT.change_matches(REAL(vgo,real64)-REAL(vgraupel,real64), &
    scale*volume_requested,vgo)) RETURN
IF (.NOT.rain_cone(qro,nro,dry_density,rain_min,rain_max) .OR. &
    .NOT.graupel_cone(qgo,vgo,graupel_density_min,graupel_density_max)) RETURN
ok=.TRUE.
END SUBROUTINE candidate

PURE LOGICAL FUNCTION change_matches(actual,requested,new_value)
REAL(real64), INTENT(IN) :: actual,requested
REAL(real32), INTENT(IN) :: new_value
REAL(real64) :: tolerance
! The old REAL32 endpoint is exact in REAL64. Only the new stored endpoint
! rounds, so the storage allowance is half an ULP at that endpoint.
tolerance=0.5_real64*endpoint_ulp(new_value)+32.0_real64*EPSILON(0.0_real64)* &
          MAX(ABS(actual),ABS(requested),ABS(REAL(new_value,real64)))
change_matches=ABS(actual-requested)<=tolerance
END FUNCTION change_matches

PURE REAL(real64) FUNCTION endpoint_ulp(value)
REAL(real32), INTENT(IN) :: value
REAL(real32) :: next_value
IF (value>=HUGE(value)) THEN
  endpoint_ulp=REAL(SPACING(value),real64)
ELSEIF (value<TINY(value)) THEN
  next_value=NEAREST(value,1.0_real32)
  endpoint_ulp=REAL(next_value,real64)-REAL(value,real64)
ELSE
  endpoint_ulp=REAL(SPACING(value),real64)
ENDIF
END FUNCTION endpoint_ulp

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
       (q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired

PURE LOGICAL FUNCTION rain_cone(q,n,rho,mmin,mmax)
REAL(real32), INTENT(IN) :: q,n,rho
REAL(real64), INTENT(IN) :: mmin,mmax
REAL(real64) :: mean_mass,lo_tol,hi_tol
rain_cone=.FALSE.
IF (q==0.0_real32 .AND. n==0.0_real32) THEN
  rain_cone=.TRUE.; RETURN
ENDIF
IF (q<=0.0_real32 .OR. n<=0.0_real32) RETURN
mean_mass=REAL(rho,real64)*REAL(q,real64)/REAL(n,real64)
lo_tol=8.0_real64*REAL(SPACING(REAL(mmin,real32)),real64)
hi_tol=8.0_real64*REAL(SPACING(REAL(mmax,real32)),real64)
rain_cone=ieee_is_finite(mean_mass) .AND. mean_mass>=mmin-lo_tol .AND. mean_mass<=mmax+hi_tol
END FUNCTION rain_cone

PURE LOGICAL FUNCTION graupel_cone(q,v,rho_min,rho_max)
REAL(real32), INTENT(IN) :: q,v
REAL(real64), INTENT(IN) :: rho_min,rho_max
REAL(real64) :: density
graupel_cone=.FALSE.
IF (q==0.0_real32 .AND. v==0.0_real32) THEN
  graupel_cone=.TRUE.; RETURN
ENDIF
IF (q<=0.0_real32 .OR. v<=0.0_real32) RETURN
density=REAL(q,real64)/REAL(v,real64)
! ProgB_param tests QG/BG against exact [100,900] bounds; match that
! consumer predicate so an admitted endpoint cannot fail on the next call.
graupel_cone=ieee_is_finite(density) .AND. &
             density>=rho_min .AND. density<=rho_max
END FUNCTION graupel_cone

END SUBROUTINE pr85_kdm6_rain_freezing_packet
