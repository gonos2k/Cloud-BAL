! Independent C-grid wind reference for the bounded full-metgrid case.
!
! WPS first applies nearest-neighbour interpolation to grid-relative U/V on
! their target staggered coordinates, then rotates the target pair to Earth
! relative and back to grid relative.  This module writes those operations
! directly and does not call WPS projection or rotation routines.
MODULE qbal_metgrid_wind_reference
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  IMPLICIT NONE
  PRIVATE

  INTEGER, PARAMETER :: NSX=6,NSY=6,NTUX=5,NTUY=4,NTVX=4,NTVY=5
  REAL(real64), PARAMETER :: PI=3.1415926535897932384626433832795_real64
  REAL(real64), PARAMETER :: DEG2RAD=PI/180._real64
  REAL(real64), PARAMETER :: STANDARD_LON=127._real64
  REAL(real64), PARAMETER :: CONE=SIN(45._real64*DEG2RAD)

  PUBLIC :: reference_winds

CONTAINS

  SUBROUTINE reference_winds(source_u,source_v,target_lon_u,target_lon_v,expected_u,expected_v)
    REAL(real32), INTENT(IN) :: source_u(NSX,NSY),source_v(NSX,NSY)
    REAL(real32), INTENT(IN) :: target_lon_u(NTUX,NTUY),target_lon_v(NTVX,NTVY)
    REAL(real32), INTENT(OUT) :: expected_u(NTUX,NTUY),expected_v(NTVX,NTVY)
    REAL(real64) :: su(NSX,NSY),sv(NSX,NSY)
    REAL(real64) :: tlu(NTUX,NTUY),tlv(NTVX,NTVY)
    REAL(real64) :: target_u_grid(NTUX,NTUY),target_v_grid(NTVX,NTVY)
    REAL(real64) :: target_u_earth(NTUX,NTUY),target_v_earth(NTVX,NTVY)
    REAL(real64) :: eu(NTUX,NTUY),ev(NTVX,NTVY)
    REAL(real64) :: x,y
    INTEGER :: i,j,ix,iy

    su=REAL(source_u,real64)
    sv=REAL(source_v,real64)
    tlu=REAL(target_lon_u,real64)
    tlv=REAL(target_lon_v,real64)

    ! The source fields are M-staggered in this fixture, so lltoxy has no
    ! U/V half-cell adjustment before nearest_neighbor applies NINT.  The
    ! reference-grid coordinates are U: x=1.7:5.7,y=2.2:5.2 and V:
    ! x=2.2:5.2,y=1.7:5.7. The driver verifies the actual source
    ! nearest cells separately, including the two sphere radii. No ties occur.
    DO j=1,NTUY
      y=2.2_real64+REAL(j-1,real64)
      DO i=1,NTUX
        x=1.7_real64+REAL(i-1,real64)
        ix=NINT(x)
        iy=NINT(y)
        target_u_grid(i,j)=su(ix,iy)
      END DO
    END DO

    DO j=1,NTVY
      y=1.7_real64+REAL(j-1,real64)
      DO i=1,NTVX
        x=2.2_real64+REAL(i-1,real64)
        ix=NINT(x)
        iy=NINT(y)
        target_v_grid(i,j)=sv(ix,iy)
      END DO
    END DO

    ! These are the two WPS calls after all source levels have been stored.
    CALL rotate_pair(target_u_grid,target_v_grid,tlu,tlv,1,target_u_earth,target_v_earth)
    CALL rotate_pair(target_u_earth,target_v_earth,tlu,tlv,-1,eu,ev)
    expected_u=REAL(eu,real32)
    expected_v=REAL(ev,real32)
  END SUBROUTINE reference_winds

  ! This is the C-grid part of WPS metmap_xform, written independently.
  ! idir=+1 maps grid-relative to Earth-relative; idir=-1 maps Earth-relative
  ! to grid-relative.  Both output arrays are written from the unmodified
  ! input pair, so U/V cross-component averages cannot see partial updates.
  SUBROUTINE rotate_pair(u,v,lon_u,lon_v,idir,u_new,v_new)
    REAL(real64), INTENT(IN) :: u(NTUX,NTUY),v(NTVX,NTVY)
    REAL(real64), INTENT(IN) :: lon_u(NTUX,NTUY),lon_v(NTVX,NTVY)
    INTEGER, INTENT(IN) :: idir
    REAL(real64), INTENT(OUT) :: u_new(NTUX,NTUY),v_new(NTVX,NTVY)
    REAL(real64) :: u_map,v_map,u_weight,v_weight,alpha
    INTEGER :: i,j,ivlo,ivhi,jlo,jhi

    DO j=1,NTUY
      DO i=1,NTUX
        alpha=rotation_angle(lon_u(i,j),idir)
        u_map=u(i,j)
        ivlo=MAX(1,i-1)
        ivhi=MIN(NTVX,i)
        v_map=SUM(v(ivlo:ivhi,j:j+1))
        v_weight=REAL(2*(ivhi-ivlo+1),real64)
        u_new(i,j)=COS(alpha)*u_map+SIN(alpha)*v_map/v_weight
      END DO
    END DO

    DO j=1,NTVY
      DO i=1,NTVX
        alpha=rotation_angle(lon_v(i,j),idir)
        v_map=v(i,j)
        jlo=MAX(1,j-1)
        jhi=MIN(NTUY,j)
        u_map=SUM(u(i:i+1,jlo:jhi))
        u_weight=REAL(2*(jhi-jlo+1),real64)
        v_new(i,j)=-SIN(alpha)*u_map/u_weight+COS(alpha)*v_map
      END DO
    END DO
  END SUBROUTINE rotate_pair

  REAL(real64) FUNCTION rotation_angle(lon,idir)
    REAL(real64), INTENT(IN) :: lon
    INTEGER, INTENT(IN) :: idir
    REAL(real64) :: diff

    diff=REAL(idir,real64)*(lon-STANDARD_LON)
    IF (diff>180._real64) diff=diff-360._real64
    IF (diff<-180._real64) diff=diff+360._real64
    rotation_angle=diff*CONE*DEG2RAD
  END FUNCTION rotation_angle

END MODULE qbal_metgrid_wind_reference
