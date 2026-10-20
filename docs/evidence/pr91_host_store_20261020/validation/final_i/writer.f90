module pr91_writer_stub
 use iso_fortran_env, only: real32,real64
 implicit none
 integer,parameter :: cells=1
 integer :: itimestep=77,rk=3
 logical :: source_first_pair(4)=.false.
 real(real64) :: theta=0.0_real64,minmass(4),maxmass(4),qs64(1,4),ns64(1,4),qa64(1,4),na64(1,4),number_bounds(1,2,4)
 real(real32) :: dt=0.125_real32,oldcarrier(1),newcarrier(1),qb(1,4),nb(1,4),drydensity(1)
contains
 subroutine wrf_error_fatal(message)
  character(*),intent(in) :: message
  write(*,*) trim(message)
  stop 1
 end subroutine
  SUBROUTINE write_pr91_actual_store_failures(pr91_stage,pr91_candidate,pr91_stored, &
      pr91_adjustment,pr91_scale,pr91_cells,pr91_target_i,pr91_target_j,pr91_target_k)
    INTEGER,INTENT(IN) :: pr91_stage(6,4),pr91_adjustment(6,4),pr91_cells(6)
    INTEGER,INTENT(IN) :: pr91_target_i(6),pr91_target_j(6),pr91_target_k(6)
    REAL(real64),INTENT(IN) :: pr91_candidate(6,2,4),pr91_scale(6,4)
    REAL(real32),INTENT(IN) :: pr91_stored(6,2,4)
    CHARACTER(LEN=64) :: run_id
    INTEGER :: u,ios,c,i,k,j,p,t
    OPEN(NEWUNIT=u,FILE='pr91_actual_store_failures.raw',STATUS='UNKNOWN', &
         POSITION='APPEND',ACTION='WRITE',IOSTAT=ios)
    IF (ios/=0) CALL wrf_error_fatal('PR91 trace open failed')
    CALL get_environment_variable('PR91_RUN_ID',run_id,STATUS=ios)
    IF (ios/=0.OR.LEN_TRIM(run_id)==0) CALL wrf_error_fatal('PR91_RUN_ID is required')
    WRITE(u,*) 'PR91_HOST_STORE_TRACE_V1',TRIM(run_id)
    WRITE(u,*) 'META: attempt_id,timestep,rk,pair,i,j,k,attempted_scale,dt'
    WRITE(u,*) 'R64: carriers,base,source,transport,candidate,density,mass_bounds,number_bounds,stored'
    WRITE(u,*) 'HEX64: candidate,source,transport,mass_bounds,number_bounds'
    WRITE(u,*) 'HEX32: stored,density,carriers,base,dt; tail:failure_stage,adjustment'
    WRITE(u,*) 'OPTIONS: run_id,attempt,timestep,rk,pair,i,j,k,subnormal,normal_adjust'
    WRITE(u,*) 'OPTIONS2: quantum_absence,strict_mass,inactive_limit,volume_bounds'
    WRITE(u,*) 'OPTIONS3: number_pair_bounds,strict_number_pair,inactive_value'
    DO t=1,6
      c=pr91_cells(t)
      IF (c<=0) CYCLE
      i=pr91_target_i(t); j=pr91_target_j(t); k=pr91_target_k(t)
      DO p=1,4
        IF (pr91_stage(t,p)<=0) CYCLE
        WRITE(u,'(a,1x,a,7i10,1p,19es26.17,10(1x,z16.16),8(1x,z8.8),2i6)') &
          'ACTUAL_STORE_FAILURE',TRIM(run_id),MERGE(1,0,ANY(source_first_pair)), &
          itimestep,rk,p,i,j,k,pr91_scale(t,p),dt,oldcarrier(c),newcarrier(c), &
          qb(c,p),nb(c,p),qs64(c,p),ns64(c,p),qa64(c,p),na64(c,p), &
          pr91_candidate(t,1,p),pr91_candidate(t,2,p),drydensity(c),minmass(p),maxmass(p), &
          number_bounds(c,1,p),number_bounds(c,2,p),pr91_stored(t,1,p),pr91_stored(t,2,p), &
          TRANSFER(pr91_candidate(t,1,p),0_8),TRANSFER(pr91_candidate(t,2,p),0_8), &
          TRANSFER(qs64(c,p),0_8),TRANSFER(ns64(c,p),0_8), &
          TRANSFER(qa64(c,p),0_8),TRANSFER(na64(c,p),0_8), &
          TRANSFER(minmass(p),0_8),TRANSFER(maxmass(p),0_8), &
          TRANSFER(number_bounds(c,1,p),0_8),TRANSFER(number_bounds(c,2,p),0_8), &
          TRANSFER(pr91_stored(t,1,p),0_4),TRANSFER(pr91_stored(t,2,p),0_4), &
          TRANSFER(drydensity(c),0_4),TRANSFER(oldcarrier(c),0_4),TRANSFER(newcarrier(c),0_4), &
          TRANSFER(qb(c,p),0_4),TRANSFER(nb(c,p),0_4),TRANSFER(dt,0_4), &
          pr91_stage(t,p),pr91_adjustment(t,p)
        WRITE(u,'(A,1X,A,1X,A,6(1X,I0),8(1X,L1),1X,ES26.17)') &
          'ACTUAL_STORE_OPTIONS',TRIM(run_id), &
          MERGE('SOURCE_FIRST_FALLBACK','BASELINE             ',ANY(source_first_pair)), &
          itimestep,rk,p,i,j,k,.TRUE.,.TRUE.,.TRUE.,p==4,p==2, &
          (p==1.OR.p==3).AND.ANY(number_bounds(c,:,p)/=0.0_real64),.TRUE.,.FALSE., &
          MERGE(REAL(NEAREST(1.e-14,-1.0),real64),0.0_real64,p==2)
      END DO
    END DO
    CLOSE(u)
  END SUBROUTINE write_pr91_actual_store_failures

end module
program exercise
 use iso_fortran_env, only: real32,real64
 use pr91_writer_stub
 implicit none
 integer :: stage(6,4),adjustment(6,4),target_cells(6),ti(6),tj(6),tk(6)
 real(real64) :: candidate(6,2,4),scale(6,4)
 real(real32) :: stored(6,2,4)
 minmass=1.0_real64; maxmass=9.0_real64
 qs64=0.0_real64; ns64=0.0_real64; qa64=0.0_real64; na64=0.0_real64
 number_bounds=0.0_real64; oldcarrier=1.0_real32; newcarrier=1.0_real32
 qb=2.5e-6_real32; nb=1.25e-8_real32; drydensity=1.2_real32
 stage=0; adjustment=0; candidate=0.0_real64; scale=0.0_real64; stored=0.0_real32
 target_cells=0; target_cells(1)=1
 ti=[130,194,132,196,168,231]; tj=[182,80,201,211,225,240]; tk=[2,22,19,16,20,20]
 stage(1,4)=6; candidate(1,1,4)=2.5e-6_real64; candidate(1,2,4)=1.25e-8_real64
 scale(1,4)=1.0_real64; stored(1,1,4)=2.5e-6_real32; stored(1,2,4)=1.25e-8_real32
 call write_pr91_actual_store_failures(stage,candidate,stored,adjustment,scale,target_cells,ti,tj,tk)
end program
