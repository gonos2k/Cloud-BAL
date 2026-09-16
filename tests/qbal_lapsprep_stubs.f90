! Test-only output and clock hooks for the actual cold LAPSPREP caller.
!
! The reader and WPS writer remain the upstream/maintained production sources.
! Only unused legacy output formats and the CDF observation hook are replaced
! here so the caller's arrays can be inspected without a native-model runtime.

MODULE lapsprep_mm5
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_pregrid_format
CONTAINS
  SUBROUTINE output_pregrid_format(p,t,ht,u,v,rh,slp,lwc,rai,sno,ice,pic,snocov,tskin)
    REAL, INTENT(IN) :: p(:),t(:,:,:),ht(:,:,:),u(:,:,:),v(:,:,:),rh(:,:,:)
    REAL, INTENT(IN) :: slp(:,:),lwc(:,:,:),rai(:,:,:),sno(:,:,:),ice(:,:,:),pic(:,:,:)
    REAL, INTENT(IN) :: snocov(:,:),tskin(:,:)
    ERROR STOP 'unexpected mm5 output stub call'
  END SUBROUTINE output_pregrid_format
END MODULE lapsprep_mm5

MODULE lapsprep_wrf
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_gribprep_format
CONTAINS
  SUBROUTINE output_gribprep_format(p,t,ht,u,v,rh,slp,psfc,lwc,rai,sno,ice,pic,snocov,tskin)
    REAL, INTENT(IN) :: p(:),t(:,:,:),ht(:,:,:),u(:,:,:),v(:,:,:),rh(:,:,:)
    REAL, INTENT(IN) :: slp(:,:),psfc(:,:),lwc(:,:,:),rai(:,:,:),sno(:,:,:)
    REAL, INTENT(IN) :: ice(:,:,:),pic(:,:,:),snocov(:,:),tskin(:,:)
    ERROR STOP 'unexpected wrf output stub call'
  END SUBROUTINE output_gribprep_format
END MODULE lapsprep_wrf

MODULE lapsprep_rams
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_ralph2_format
CONTAINS
  SUBROUTINE output_ralph2_format(p,u,v,t,ht,rh,slp,psfc,snocov,tskin)
    REAL, INTENT(IN) :: p(:),u(:,:,:),v(:,:,:),t(:,:,:),ht(:,:,:),rh(:,:,:)
    REAL, INTENT(IN) :: slp(:,:),psfc(:,:),snocov(:,:),tskin(:,:)
    ERROR STOP 'unexpected rams output stub call'
  END SUBROUTINE output_ralph2_format
END MODULE lapsprep_rams

MODULE lapsprep_netcdf
  USE, INTRINSIC :: iso_fortran_env, ONLY: int32
  IMPLICIT NONE
  PRIVATE
  PUBLIC output_netcdf_format
CONTAINS
  SUBROUTINE output_netcdf_format(pr,ht,tp,mr,uw,vw,ww,slp,spr,lwc,ice,rai,sno,pic)
    REAL, INTENT(IN) :: pr(:),ht(:,:,:),tp(:,:,:),mr(:,:,:),uw(:,:,:),vw(:,:,:)
    REAL, INTENT(IN) :: ww(:,:,:),slp(:,:),spr(:,:),lwc(:,:,:),ice(:,:,:)
    REAL, INTENT(IN) :: rai(:,:,:),sno(:,:,:),pic(:,:,:)
    INTEGER :: unit,ios
    INTEGER(int32) :: dimensions(3)

    IF (SIZE(pr) /= 5 .OR. ANY(SHAPE(ht) /= [6,6,5]) .OR. &
        ANY(SHAPE(tp) /= [6,6,5]) .OR. ANY(SHAPE(mr) /= [6,6,5]) .OR. &
        ANY(SHAPE(uw) /= [6,6,5]) .OR. ANY(SHAPE(vw) /= [6,6,5]) .OR. &
        ANY(SHAPE(ww) /= [6,6,5])) THEN
      ERROR STOP 'CDF reader-state shape mismatch'
    END IF

    dimensions = [6_int32,6_int32,5_int32]
    OPEN (NEWUNIT=unit,FILE='reader_state.bin',STATUS='NEW',ACTION='WRITE', &
          ACCESS='STREAM',FORM='UNFORMATTED',CONVERT='LITTLE_ENDIAN',IOSTAT=ios)
    IF (ios /= 0) ERROR STOP 'CDF reader-state open failed'
    WRITE (unit,IOSTAT=ios) dimensions
    IF (ios == 0) WRITE (unit,IOSTAT=ios) pr,ht,tp,mr,uw,vw,ww
    IF (ios /= 0) THEN
      CLOSE (unit)
      ERROR STOP 'CDF reader-state write failed'
    END IF
    CLOSE (unit,IOSTAT=ios)
    IF (ios /= 0) ERROR STOP 'CDF reader-state close failed'
  END SUBROUTINE output_netcdf_format
END MODULE lapsprep_netcdf

SUBROUTINE get_systime(i4time,laps_file_time,istatus)
  INTEGER, INTENT(OUT) :: i4time,istatus
  CHARACTER(LEN=*), INTENT(OUT) :: laps_file_time
  i4time=0
  laps_file_time=''
  istatus=0
  ERROR STOP 'unexpected get_systime call'
END SUBROUTINE get_systime

! The full caller contains an unreachable SHADOW branch in this cold test.
! Keep its legacy clock symbol linked, while rejecting accidental activation.
SUBROUTINE i4time_fname_lp(fname_in,i4time,istatus)
  CHARACTER(LEN=*), INTENT(IN) :: fname_in
  INTEGER, INTENT(OUT) :: i4time,istatus
  i4time=0
  istatus=0
  ERROR STOP 'unexpected i4time_fname_lp call'
END SUBROUTINE i4time_fname_lp

REAL FUNCTION make_rh(p,tc,mr,flag)
  REAL, INTENT(IN) :: p,tc,mr,flag
  make_rh=0.0
  ERROR STOP 'unexpected make_rh call'
END FUNCTION make_rh

SUBROUTINE saturate_ice_points(t,p,thresh,sh_m,rh_m)
  REAL, INTENT(IN) :: t,p,thresh
  REAL, INTENT(OUT) :: sh_m,rh_m
  sh_m=0.0
  rh_m=0.0
  ERROR STOP 'unexpected saturate_ice_points call'
END SUBROUTINE saturate_ice_points
