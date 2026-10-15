SUBROUTINE pr85_kdm6_subthreshold_melt(qcloud,ncloud,qrain,nrain,dry_density, &
delz,qmelt,snow_mean_mass,cloud_min,cloud_max,rain_min,rain_max, &
qcloud_after,ncloud_after,qrain_after,nrain_after,number_requested, &
route,accepted)
USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
IMPLICIT NONE
REAL(real32), INTENT(IN) :: qcloud,ncloud,qrain,nrain,dry_density,delz,qmelt
REAL(real32), INTENT(IN) :: snow_mean_mass,cloud_min,cloud_max,rain_min,rain_max
REAL(real32), INTENT(OUT) :: qcloud_after,ncloud_after,qrain_after,nrain_after
REAL(real64), INTENT(OUT) :: number_requested
INTEGER, INTENT(OUT) :: route
LOGICAL, INTENT(OUT) :: accepted

REAL(real64) :: source_mass,source_number
REAL(real64) :: mean_mass,r32max
REAL(real32) :: qstored,nstored
LOGICAL :: source_fits_cloud,source_fits_rain

qcloud_after=qcloud
ncloud_after=ncloud
qrain_after=qrain
nrain_after=nrain
number_requested=0.0_real64
route=0
accepted=.FALSE.
IF (.NOT.ALL(ieee_is_finite([qcloud,ncloud,qrain,nrain,dry_density,delz,qmelt, &
    snow_mean_mass,cloud_min,cloud_max,rain_min,rain_max]))) RETURN
IF (MIN(qcloud,ncloud,qrain,nrain)<0.0_real32 .OR. dry_density<=0.0_real32 .OR. &
    delz<=0.0_real32 .OR. qmelt<0.0_real32 .OR. snow_mean_mass<=0.0_real32 .OR. &
    cloud_min<=0.0_real32 .OR. cloud_max<cloud_min .OR. rain_min<=0.0_real32 .OR. &
    rain_max<rain_min) RETURN
IF (.NOT.paired(qcloud,ncloud) .OR. .NOT.paired(qrain,nrain)) RETURN
IF (qmelt==0.0_real32) THEN
  accepted=.TRUE.
  RETURN
ENDIF

source_mass=REAL(snow_mean_mass,real64)
source_number=REAL(dry_density,real64)*REAL(qmelt,real64)/source_mass
IF (.NOT.ieee_is_finite(source_number) .OR. source_number<=0.0_real64) RETURN
number_requested=source_number
source_fits_cloud=snow_mean_mass>=cloud_min .AND. snow_mean_mass<=cloud_max
source_fits_rain=snow_mean_mass>=rain_min .AND. snow_mean_mass<=rain_max
r32max=REAL(HUGE(0.0_real32),real64)

IF (source_fits_cloud) THEN
  CALL try_category(qcloud,ncloud,cloud_min,cloud_max,ok=accepted, &
       qstored=qstored,nstored=nstored)
  IF (accepted) THEN
    route=1
    qcloud_after=qstored
    ncloud_after=nstored
    RETURN
  ENDIF
ENDIF
IF (source_fits_rain) THEN
  CALL try_category(qrain,nrain,rain_min,rain_max,ok=accepted, &
       qstored=qstored,nstored=nstored)
  IF (accepted) THEN
    route=2
    qrain_after=qstored
    nrain_after=nstored
    RETURN
  ENDIF
ENDIF
route=0
accepted=.FALSE.

CONTAINS

SUBROUTINE try_category(qold,nold,mean_min,mean_max,ok,qstored,nstored)
REAL(real32), INTENT(IN) :: qold,nold,mean_min,mean_max
LOGICAL, INTENT(OUT) :: ok
REAL(real32), INTENT(OUT) :: qstored,nstored
REAL(real64) :: qtrial,ntrial
qstored=qold
nstored=nold
ok=.FALSE.
qtrial=REAL(qold,real64)+REAL(qmelt,real64)
ntrial=REAL(nold,real64)+source_number
IF (.NOT.ieee_is_finite(qtrial) .OR. .NOT.ieee_is_finite(ntrial)) RETURN
IF (qtrial<=0.0_real64 .OR. ntrial<=0.0_real64 .OR. &
    qtrial>r32max .OR. ntrial>r32max) RETURN
mean_mass=REAL(dry_density,real64)*qtrial/ntrial
IF (.NOT.ieee_is_finite(mean_mass) .OR. &
    mean_mass<REAL(mean_min,real64) .OR. mean_mass>REAL(mean_max,real64)) RETURN
qstored=REAL(qtrial,real32)
nstored=REAL(ntrial,real32)
IF (.NOT.ieee_is_finite(qstored) .OR. .NOT.ieee_is_finite(nstored)) RETURN
IF (.NOT.paired(qstored,nstored)) RETURN
mean_mass=REAL(dry_density,real64)*REAL(qstored,real64)/REAL(nstored,real64)
IF (.NOT.ieee_is_finite(mean_mass) .OR. &
    mean_mass<REAL(mean_min,real64) .OR. mean_mass>REAL(mean_max,real64)) RETURN
ok=.TRUE.
END SUBROUTINE try_category

PURE LOGICAL FUNCTION paired(q,n)
REAL(real32), INTENT(IN) :: q,n
paired=(q==0.0_real32 .AND. n==0.0_real32) .OR. &
       (q>0.0_real32 .AND. n>0.0_real32)
END FUNCTION paired

END SUBROUTINE pr85_kdm6_subthreshold_melt
