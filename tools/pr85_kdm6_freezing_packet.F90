SUBROUTINE pr85_kdm6_freezing_packet(qcloud,ncloud,qice,nice,dry_density,ice_transient_mass_limit, &
mass_requested,number_requested,cloud_min,cloud_max,ice_min,ice_max, &
qcloud_after,ncloud_after,qice_after,nice_after,mass_approved, &
number_approved,fraction,base_valid,accepted)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL(real32), INTENT(IN) :: qcloud,ncloud,qice,nice,dry_density
REAL(real64), INTENT(IN) :: ice_transient_mass_limit
REAL(real64), INTENT(IN) :: mass_requested,number_requested
REAL(real64), INTENT(IN) :: cloud_min,cloud_max,ice_min,ice_max
REAL(real32), INTENT(OUT) :: qcloud_after,ncloud_after,qice_after,nice_after
REAL(real64), INTENT(OUT) :: mass_approved,number_approved,fraction
LOGICAL, INTENT(OUT) :: base_valid,accepted

REAL(real64) :: theta
REAL(real32) :: qct,nct,qit,nit
LOGICAL :: feasible,found
INTEGER :: attempt

qcloud_after=qcloud
ncloud_after=ncloud
qice_after=qice
nice_after=nice
mass_approved=0.0_real64
number_approved=0.0_real64
fraction=0.0_real64
base_valid=.FALSE.
accepted=.FALSE.
IF (.NOT.ALL(ieee_is_finite([qcloud,ncloud,qice,nice,dry_density]))) RETURN
IF (.NOT.ieee_is_finite(ice_transient_mass_limit)) RETURN
IF (.NOT.ALL(ieee_is_finite([mass_requested,number_requested,cloud_min,cloud_max, &
    ice_min,ice_max]))) RETURN
IF (MIN(qcloud,ncloud,qice,nice)<0.0_real32 .OR. dry_density<=0.0_real32 .OR. &
    ice_transient_mass_limit<0.0_real64 .OR. &
    mass_requested<0.0_real64 .OR. number_requested<0.0_real64 .OR. &
    cloud_min<=0.0_real64 .OR. cloud_max<cloud_min .OR. &
    ice_min<=0.0_real64 .OR. ice_max<ice_min) RETURN
IF (MIN(cloud_min,ice_min)<REAL(TINY(0.0_real32),real64) .OR. &
    MAX(cloud_max,ice_max)>REAL(HUGE(0.0_real32),real64)) RETURN
IF (.NOT.paired(qcloud,ncloud) .OR. .NOT.paired(qice,nice)) RETURN
IF (.NOT.in_cone(qcloud,ncloud,dry_density,cloud_min,cloud_max)) RETURN
IF (qice>0.0_real32 .AND. REAL(qice,real64)<=ice_transient_mass_limit) THEN
  ! Native KDM6 skips ice PSD reconstruction below the 1.e-14 mass gate.
  ! Admit only that source-bounded base category;
  ! candidate endpoints still pass the strict ice cone below.
ELSE
  IF (.NOT.in_cone(qice,nice,dry_density,ice_min,ice_max)) RETURN
ENDIF
base_valid=.TRUE.
IF (mass_requested==0.0_real64 .AND. number_requested==0.0_real64) THEN
  accepted=.TRUE.
  RETURN
ENDIF
IF (mass_requested<=0.0_real64 .OR. number_requested<=0.0_real64) RETURN

! Full source proposal is preferred. If storage/PSD constraints require it,
! deterministic halving seeks a representable paired fraction.
theta=1.0_real64
found=.FALSE.
DO attempt=0,48
  CALL candidate(theta,qct,nct,qit,nit,feasible)
  IF (feasible) THEN
    found=.TRUE.
    EXIT
  ENDIF
  theta=theta*0.5_real64
ENDDO
IF (.NOT.found) RETURN
qcloud_after=qct
ncloud_after=nct
qice_after=qit
nice_after=nit
fraction=theta
mass_approved=theta*mass_requested
number_approved=theta*number_requested
accepted=.TRUE.

CONTAINS

SUBROUTINE candidate(scale,qco,nco,qio,nio,ok)
REAL(real64), INTENT(IN) :: scale
REAL(real32), INTENT(OUT) :: qco,nco,qio,nio
LOGICAL, INTENT(OUT) :: ok
REAL(real64) :: qcd,ncd,qid,nid,r32max,mass_amount,number_amount
qco=qcloud; nco=ncloud; qio=qice; nio=nice
ok=.FALSE.
r32max=REAL(HUGE(0.0_real32),real64)
qcd=REAL(qcloud,real64)-scale*mass_requested
ncd=REAL(ncloud,real64)-scale*number_requested
qid=REAL(qice,real64)+scale*mass_requested
nid=REAL(nice,real64)+scale*number_requested
IF (.NOT.ALL(ieee_is_finite([qcd,ncd,qid,nid]))) RETURN
IF (MIN(qcd,ncd,qid,nid)<0.0_real64 .OR. MAX(qcd,ncd,qid,nid)>r32max) RETURN
qco=REAL(qcd,real32); nco=REAL(ncd,real32)
qio=REAL(qid,real32); nio=REAL(nid,real32)
IF (.NOT.ALL(ieee_is_finite([qco,nco,qio,nio]))) RETURN
IF (.NOT.paired(qco,nco) .OR. .NOT.paired(qio,nio)) RETURN
! A positive packet must be stored on both sides for each moment.
IF (qco>=qcloud .OR. nco>=ncloud .OR. qio<=qice .OR. nio<=nice) RETURN
mass_amount=scale*mass_requested
number_amount=scale*number_requested
IF (.NOT.change_matches_packet(REAL(qcloud,real64)-REAL(qco,real64), &
    mass_amount,qco)) RETURN
IF (.NOT.change_matches_packet(REAL(qio,real64)-REAL(qice,real64), &
    mass_amount,qio)) RETURN
IF (.NOT.change_matches_packet(REAL(ncloud,real64)-REAL(nco,real64), &
    number_amount,nco)) RETURN
IF (.NOT.change_matches_packet(REAL(nio,real64)-REAL(nice,real64), &
    number_amount,nio)) RETURN
IF (.NOT.in_cone(qco,nco,dry_density,cloud_min,cloud_max) .OR. &
    .NOT.in_cone(qio,nio,dry_density,ice_min,ice_max)) RETURN
ok=.TRUE.
END SUBROUTINE candidate

PURE LOGICAL FUNCTION change_matches_packet(actual,requested,new_value)
REAL(real64), INTENT(IN) :: actual,requested
REAL(real32), INTENT(IN) :: new_value
REAL(real64) :: tolerance
! The old REAL32 endpoint is exact in REAL64; only the new stored endpoint
! rounds, so use half an ULP at the new endpoint.
tolerance=0.5_real64*endpoint_ulp(new_value)+ &
          32.0_real64*EPSILON(0.0_real64)* &
          MAX(ABS(actual),ABS(requested),ABS(REAL(new_value,real64)))
change_matches_packet=ABS(actual-requested)<=tolerance
END FUNCTION change_matches_packet

PURE REAL(real64) FUNCTION endpoint_ulp(value)
REAL(real32), INTENT(IN) :: value
REAL(real32) :: next_value
IF (value<TINY(0.0_real32)) THEN
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

PURE LOGICAL FUNCTION in_cone(q,n,rho,mmin,mmax)
REAL(real32), INTENT(IN) :: q,n,rho
REAL(real64), INTENT(IN) :: mmin,mmax
REAL(real64) :: mean_mass,lo_tol,hi_tol
in_cone=.FALSE.
IF (q==0.0_real32 .AND. n==0.0_real32) THEN
  in_cone=.TRUE.
  RETURN
ENDIF
IF (q<=0.0_real32 .OR. n<=0.0_real32) RETURN
mean_mass=REAL(rho,real64)*REAL(q,real64)/REAL(n,real64)
lo_tol=8.0_real64*REAL(SPACING(REAL(mmin,real32)),real64)
hi_tol=8.0_real64*REAL(SPACING(REAL(mmax,real32)),real64)
in_cone=ieee_is_finite(mean_mass) .AND. &
        mean_mass>=mmin-lo_tol .AND. mean_mass<=mmax+hi_tol
END FUNCTION in_cone

END SUBROUTINE pr85_kdm6_freezing_packet
