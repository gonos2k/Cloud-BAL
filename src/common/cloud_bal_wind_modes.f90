! Discrete divergent/rotational diagnostics for localized wind increments.
MODULE cloud_bal_wind_modes
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: diagnose_wind_increment_modes

CONTAINS

  SUBROUTINE diagnose_wind_increment_modes(u0,v0,u1,v1,influence,dx,dy, &
       divergence_rms,vorticity_rms,divergence_roughness_rms, &
       divergence_profile,vorticity_profile,status)
    REAL, INTENT(IN) :: u0(:,:,:),v0(:,:,:),u1(:,:,:),v1(:,:,:)
    REAL, INTENT(IN) :: influence(:,:,:),dx(:,:),dy(:,:)
    REAL, INTENT(OUT) :: divergence_rms,vorticity_rms
    REAL, INTENT(OUT) :: divergence_roughness_rms
    REAL, INTENT(OUT) :: divergence_profile(:),vorticity_profile(:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: nx,ny,nz,i,j,k,n,nrough
    INTEGER, ALLOCATABLE :: nlevel(:)
    REAL, ALLOCATABLE :: divergence(:,:,:),vorticity(:,:,:)
    REAL :: du_here,du_west,dv_here,dv_south,du_south,dv_west
    REAL :: weight,divsum,vortsum,roughsum,lap

    status=0
    divergence_rms=0.0
    vorticity_rms=0.0
    divergence_roughness_rms=0.0
    divergence_profile=0.0
    vorticity_profile=0.0
    nx=SIZE(u0,1); ny=SIZE(u0,2); nz=SIZE(u0,3)
    IF (nx < 3 .OR. ny < 3 .OR. nz < 1 .OR. &
        ANY(SHAPE(u0)/=SHAPE(v0)) .OR. ANY(SHAPE(u0)/=SHAPE(u1)) .OR. &
        ANY(SHAPE(u0)/=SHAPE(v1)) .OR. &
        ANY(SHAPE(u0)/=SHAPE(influence)) .OR. &
        SIZE(dx,1)/=nx .OR. SIZE(dx,2)/=ny .OR. &
        SIZE(dy,1)/=nx .OR. SIZE(dy,2)/=ny .OR. &
        SIZE(divergence_profile)/=nz .OR. SIZE(vorticity_profile)/=nz) RETURN
    IF (ANY(.NOT. ieee_is_finite(u0)) .OR. ANY(.NOT. ieee_is_finite(v0)) .OR. &
        ANY(.NOT. ieee_is_finite(u1)) .OR. ANY(.NOT. ieee_is_finite(v1)) .OR. &
        ANY(.NOT. ieee_is_finite(influence)) .OR. MINVAL(influence)<0.0 .OR. &
        MAXVAL(influence)>1.0 .OR. ANY(.NOT. ieee_is_finite(dx)) .OR. &
        ANY(dx<=0.0) .OR. ANY(.NOT. ieee_is_finite(dy)) .OR. ANY(dy<=0.0)) &
      RETURN

    ALLOCATE(divergence(nx,ny,nz),vorticity(nx,ny,nz),nlevel(nz))
    divergence=0.0
    vorticity=0.0
    nlevel=0
    divsum=0.0
    vortsum=0.0
    n=0
    DO k=1,nz
      DO j=2,ny
        DO i=2,nx
          weight=influence(i,j,k)
          IF (weight<=0.0) CYCLE
          du_here=u1(i,j,k)-u0(i,j,k)
          du_west=u1(i-1,j,k)-u0(i-1,j,k)
          dv_here=v1(i,j,k)-v0(i,j,k)
          dv_south=v1(i,j-1,k)-v0(i,j-1,k)
          du_south=u1(i,j-1,k)-u0(i,j-1,k)
          dv_west=v1(i-1,j,k)-v0(i-1,j,k)
          divergence(i,j,k)=weight*((du_here-du_west)/dx(i,j)+ &
                                    (dv_here-dv_south)/dy(i,j))
          vorticity(i,j,k)=weight*((dv_here-dv_west)/dx(i,j)- &
                                   (du_here-du_south)/dy(i,j))
          divsum=divsum+divergence(i,j,k)**2
          vortsum=vortsum+vorticity(i,j,k)**2
          divergence_profile(k)=divergence_profile(k)+divergence(i,j,k)
          vorticity_profile(k)=vorticity_profile(k)+vorticity(i,j,k)
          nlevel(k)=nlevel(k)+1
          n=n+1
        END DO
      END DO
    END DO
    IF (n==0) THEN
      status=2
      DEALLOCATE(divergence,vorticity,nlevel)
      RETURN
    END IF
    divergence_rms=SQRT(divsum/REAL(n))
    vorticity_rms=SQRT(vortsum/REAL(n))
    DO k=1,nz
      IF (nlevel(k)>0) THEN
        divergence_profile(k)=divergence_profile(k)/REAL(nlevel(k))
        vorticity_profile(k)=vorticity_profile(k)/REAL(nlevel(k))
      END IF
    END DO

    roughsum=0.0
    nrough=0
    DO k=1,nz
      DO j=3,ny-1
        DO i=3,nx-1
          IF (influence(i,j,k)<=0.0) CYCLE
          lap=(divergence(i+1,j,k)-2.0*divergence(i,j,k)+ &
               divergence(i-1,j,k))/dx(i,j)**2+ &
              (divergence(i,j+1,k)-2.0*divergence(i,j,k)+ &
               divergence(i,j-1,k))/dy(i,j)**2
          roughsum=roughsum+lap*lap
          nrough=nrough+1
        END DO
      END DO
    END DO
    IF (nrough>0) divergence_roughness_rms=SQRT(roughsum/REAL(nrough))
    IF (.NOT. ieee_is_finite(divergence_rms) .OR. &
        .NOT. ieee_is_finite(vorticity_rms) .OR. &
        .NOT. ieee_is_finite(divergence_roughness_rms)) THEN
      divergence_rms=0.0; vorticity_rms=0.0
      divergence_roughness_rms=0.0
      divergence_profile=0.0; vorticity_profile=0.0
      DEALLOCATE(divergence,vorticity,nlevel)
      RETURN
    END IF
    status=1
    DEALLOCATE(divergence,vorticity,nlevel)
  END SUBROUTINE diagnose_wind_increment_modes

END MODULE cloud_bal_wind_modes
