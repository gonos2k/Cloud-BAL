#!/usr/bin/env python3
"""Add read-only first-failure traces to copied PR76 native sources."""

from __future__ import annotations

import re

from pr76_native_fp_transform import transform as transform_pr76


ENTRY_CHECK = "   call validate_kdm6_species_states(qci,qrs,nrs,nci,brs)\n"
SLOPE_CHECK = "   call validate_kdm6_slope_states(qci,qrs,nrs,nci,brs, &\n"
LOCAL_CHECK = "          call validate_local_species_states(qrs(i,k,1),nrs(i,k,1), &\n"
KDM62D_EXECUTABLE = "   idim = ite-its+1\n"
MODULE_END = "END MODULE module_mp_kdm6\n"


def transform(source: str) -> str:
    """Add observers immediately before each unchanged KDM6 state validator."""
    source = transform_pr76(source, gradual=True)
    if (source.count(ENTRY_CHECK) != 1 or source.count(SLOPE_CHECK) != 7
            or source.count(LOCAL_CHECK) != 3
            or source.count(KDM62D_EXECUTABLE) != 1
            or source.count(MODULE_END) != 1):
        raise ValueError("unexpected KDM6 validator or declaration anchors")

    source = source.replace(
        ENTRY_CHECK,
        "   call pr77_scan_entry_state(qci,qrs,nrs,nci,brs,its,ite,kts,kte,lat)\n"
        + ENTRY_CHECK,
        1,
    )

    slope_index = 0

    def observe_slope(match: re.Match[str]) -> str:
        nonlocal slope_index
        slope_index += 1
        return (
            f"   call pr77_scan_slope_state(qci,qrs,nrs,nci,brs, &\n"
            f"        qrs_tmp,nrs_tmp,qci_tmp,nci_tmp,its,ite,kts,kte,lat, &\n"
            f"        'KDM62D_SLOPE_{slope_index:02d}')\n"
            + match.group(0)
        )

    source = re.sub(re.escape(SLOPE_CHECK), observe_slope, source)

    local_index = 0

    def observe_local(match: re.Match[str]) -> str:
        nonlocal local_index
        local_index += 1
        return (
            f"          call pr77_scan_local_state(qrs(i,k,1),nrs(i,k,1), &\n"
            f"               qci(i,k,1),nci(i,k,1),qci(i,k,2),nci(i,k,2), &\n"
            f"               qrs(i,k,3),brs(i,k),i,k,lat,'KDM62D_LOCAL_{local_index:02d}')\n"
            + match.group(0)
        )

    source = re.sub(re.escape(LOCAL_CHECK), observe_local, source)

    source = source.replace(MODULE_END, _KDM6_OBSERVERS + MODULE_END, 1)
    return source


def transform_host_main(source: str) -> str:
    """Set gradual underflow on the native main thread and startup OpenMP team."""
    anchors = (
        "   USE module_wrf_top, only : wrf_init, wrf_dfi, wrf_run, wrf_finalize\n",
        "   IMPLICIT NONE\n",
        "  CALL wrf_init\n",
        "END PROGRAM wrf\n",
    )
    if (not source.lstrip().startswith("PROGRAM wrf\n")
            or any(source.count(anchor) != 1 for anchor in anchors)):
        raise ValueError("unexpected copied WRF main source anchors")

    source = source.replace(
        anchors[0],
        anchors[0]
        + "   USE, INTRINSIC :: iso_c_binding, only : c_int\n",
        1,
    )
    source = source.replace(
        anchors[1],
        anchors[1]
        + "   interface\n"
        + "      function pr76_apply_gradual(after, thread_id) &\n"
        + "          bind(C, name='pr76_apply_gradual') result(mxcsr)\n"
        + "        import :: c_int\n"
        + "        integer(c_int) :: after, thread_id, mxcsr\n"
        + "      end function pr76_apply_gradual\n"
        + "   end interface\n",
        1,
    )
    policy = """  call pr77_apply_and_log('MAIN_STARTUP')
!$omp parallel
  call pr77_apply_and_log('OMP_STARTUP_TEAM')
!$omp end parallel

"""
    source = source.replace(anchors[2], policy + anchors[2], 1)
    internal_procedure = """CONTAINS

  SUBROUTINE pr77_apply_and_log(stage)
    CHARACTER(LEN=*), INTENT(IN) :: stage
    INTEGER :: unit, ios
    INTEGER(c_int) :: mxcsr_before, mxcsr_after
    INTEGER(c_int) :: thread_id
    mxcsr_before = pr76_apply_gradual(mxcsr_after, thread_id)
!$omp critical(pr77_host_fp_log)
    OPEN(NEWUNIT=unit, FILE='pr77_host_fp.raw', STATUS='UNKNOWN', &
         POSITION='APPEND', ACTION='WRITE', IOSTAT=ios)
    IF (ios == 0) THEN
      WRITE(unit,'(A,",",A,",",Z8.8,",",Z8.8,",",I0)') &
          'PR77_HOST_FP', TRIM(stage), mxcsr_before, mxcsr_after, thread_id
      CLOSE(unit)
    END IF
!$omp end critical(pr77_host_fp_log)
  END SUBROUTINE pr77_apply_and_log

"""
    source = source.replace(anchors[3], internal_procedure + anchors[3], 1)
    return source


_KDM6_OBSERVERS = """    subroutine pr77_scan_entry_state(qci,qrs,nrs,nci,brs,its,ite,kts,kte,lat)
      real, intent(in) :: qci(:,:,:),qrs(:,:,:),nrs(:,:,:),nci(:,:,:),brs(:,:)
      integer, intent(in) :: its,ite,kts,kte,lat
      integer :: i,k,counts(5,4),unit,ios
      counts=0
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          call pr77_count_state(qrs(i,k,1),nrs(i,k,1),counts(:,1), &
               'rain',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
          call pr77_count_state(qci(i,k,1),nci(i,k,1),counts(:,2), &
               'cloud',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
          call pr77_count_state(qci(i,k,2),nci(i,k,2),counts(:,3), &
               'ice',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
          call pr77_count_state(qrs(i,k,3),brs(i,k),counts(:,4), &
               'graupel',its+i-1,kts+k-1,lat,'KDM62D_ENTRY')
        enddo
      enddo
!$omp critical(pr77_species_log)
      open(newunit=unit,file='pr77_native_species.raw', &
           status='unknown',position='append',action='write',iostat=ios)
      if (ios == 0) then
        write(unit,'(A,5(",",I0),20(",",I0))') 'PR77_COUNTS', &
             lat,its,ite,kts,kte,counts(:,1),counts(:,2),counts(:,3),counts(:,4)
        close(unit)
      endif
!$omp end critical(pr77_species_log)
    end subroutine pr77_scan_entry_state

    subroutine pr77_scan_slope_state(qci_current,qrs_current,nrs_current,nci_current, &
        brs,qrs,nrs,qci,nci,its,ite,kts,kte,lat,stage)
      real, intent(in) :: qci_current(:,:,:),qrs_current(:,:,:),nrs_current(:,:,:)
      real, intent(in) :: nci_current(:,:,:),brs(:,:),qrs(:,:,:),nrs(:,:),qci(:,:),nci(:,:)
      integer, intent(in) :: its,ite,kts,kte,lat
      character(len=*), intent(in) :: stage
      integer :: i,k
      do k=1,size(qrs,2)
        do i=1,size(qrs,1)
          call pr77_record_first(qrs_current(i,k,1),nrs_current(i,k,1), &
               'rain',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qci_current(i,k,1),nci_current(i,k,1), &
               'cloud',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qci_current(i,k,2),nci_current(i,k,2), &
               'ice',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qrs_current(i,k,3),brs(i,k), &
               'graupel',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qrs(i,k,1),nrs(i,k), &
               'rain_candidate',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qci(i,k),nci(i,k), &
               'ice_candidate',its+i-1,kts+k-1,lat,stage)
          call pr77_record_first(qrs(i,k,3),brs(i,k), &
               'graupel_candidate',its+i-1,kts+k-1,lat,stage)
        enddo
      enddo
    end subroutine pr77_scan_slope_state

    subroutine pr77_scan_local_state(qr,nr,qc,nc,qi,ni,qg,bg,i,k,lat,stage)
      real, intent(in) :: qr,nr,qc,nc,qi,ni,qg,bg
      integer, intent(in) :: i,k,lat
      character(len=*), intent(in) :: stage
      call pr77_record_first(qr,nr,'rain',i,k,lat,stage)
      call pr77_record_first(qc,nc,'cloud',i,k,lat,stage)
      call pr77_record_first(qi,ni,'ice',i,k,lat,stage)
      call pr77_record_first(qg,bg,'graupel',i,k,lat,stage)
    end subroutine pr77_scan_local_state

    subroutine pr77_count_state(mass,moment,counts,species,i,k,lat,stage)
      real, intent(in) :: mass,moment
      integer, intent(inout) :: counts(5)
      character(len=*), intent(in) :: species,stage
      integer, intent(in) :: i,k,lat
      integer :: state
      state=classify_species_state(mass,moment)
      counts(state+1)=counts(state+1)+1
      call pr77_record_first(mass,moment,species,i,k,lat,stage)
    end subroutine pr77_count_state

    subroutine pr77_record_first(mass,moment,species,i,k,lat,stage)
      real, intent(in) :: mass,moment
      character(len=*), intent(in) :: species,stage
      integer, intent(in) :: i,k,lat
      integer, save :: written=0
      integer :: state,unit,ios,thread_id
      integer(c_int) :: mxcsr
      state=classify_species_state(mass,moment)
      if (state == SPECIES_ABSENT .or. state == SPECIES_ACTIVE) return
!$omp critical(pr77_species_log)
      if (written == 0) then
        mxcsr=pr75_read_fp_state(thread_id)
        open(newunit=unit,file='pr77_native_species.raw',status='unknown', &
             position='append',action='write',iostat=ios)
        if (ios == 0) then
          write(unit,'(A,",",A,",",A,5(",",I0),2(",",ES24.16E3), &
               3(",",Z8.8))') 'PR77_FIRST',trim(stage),trim(species), &
               state,i,lat,k,thread_id,mass,moment,transfer(mass,0), &
               transfer(moment,0),mxcsr
          close(unit)
          written=1
        endif
      endif
!$omp end critical(pr77_species_log)
    end subroutine pr77_record_first

"""
