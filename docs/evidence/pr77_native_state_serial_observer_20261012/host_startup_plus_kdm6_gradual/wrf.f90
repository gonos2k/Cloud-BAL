


PROGRAM wrf

   USE module_wrf_top, only : wrf_init, wrf_dfi, wrf_run, wrf_finalize
   USE, INTRINSIC :: iso_c_binding, only : c_int











   IMPLICIT NONE
   interface
      function pr76_apply_gradual(after, thread_id) &
          bind(C, name='pr76_apply_gradual') result(mxcsr)
        import :: c_int
        integer(c_int) :: after, thread_id, mxcsr
      end function pr76_apply_gradual
   end interface


  
  call pr77_apply_and_log('MAIN_STARTUP')
!$omp parallel
  call pr77_apply_and_log('OMP_STARTUP_TEAM')
!$omp end parallel

  CALL wrf_init

  
  CALL wrf_dfi


  
  CALL wrf_run


  
  CALL wrf_finalize

CONTAINS

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

END PROGRAM wrf


