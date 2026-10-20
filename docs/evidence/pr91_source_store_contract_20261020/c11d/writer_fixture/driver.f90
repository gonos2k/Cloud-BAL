
program test_c11_capture
  use iso_fortran_env, only: int32,int64,real32,real64
  use pr87_horizontal_diffusion64, only: horizontal_diffusion64
  implicit none
  integer :: itimestep,rk,p,i,j,k,cell,stage_diag_u,stage_diag_dx,stage_diag_dy
  integer :: ims,ime,kms,kme,jms,jme
  real(real32) :: dt,rdx,rdy,c1(1),c2(1)
  real(real32) :: oldcarrier(1),newcarrier(1),drydensity(1),qb(1,1),nb(1,1)
  real(real32) :: prepared_q(1:5,1:1,1:5,1),prepared_n(1:5,1:1,1:5,1)
  real(real32) :: mut_diff(1:5,1:5),xkmhd_diff(1:5,1:1,1:5)
  real(real32) :: msfux_diff(1:5,1:5),msfuy_diff(1:5,1:5)
  real(real32) :: msfvx_inv_diff(1:5,1:5),msfvy_diff(1:5,1:5)
  real(real32) :: msftx(1:5,1:5),msfty(1:5,1:5)
  real(real64) :: source_sum64(2),qs64(1,1),ns64(1,1),stage_diag_qdiff,stage_diag_ndiff
  real(real64) :: prepared_diffusion(1:5,1:1,1:5),prepared_n_diffusion(1:5,1:1,1:5)
  real(real64) :: pr87_later_qsrc(1:5,1:1,1:5,1),pr87_later_nsrc(1:5,1:1,1:5,1)
  real(real64) :: pr87_all_pair_diffusion_delta(1:5,1:1,1:5,8)
  real(real64) :: pr87_all_pair_diffusion_old(1:5,1:1,1:5,4)
  real(real64) :: minmass(1),maxmass(1),number_bounds(1,2,1)
  ims=1; ime=5; kms=1; kme=1; jms=1; jme=5
  itimestep=2; rk=3; p=1; i=3; j=3; k=1; cell=1
  dt=20.0_real32; rdx=1.0_real32; rdy=1.0_real32; c1=1.0_real32; c2=0.0_real32
  oldcarrier=1.25_real32; newcarrier=1.5_real32; drydensity=0.9_real32
  qb=2.0_real32; nb=3.0_real32; source_sum64=[-1.0_real64,3.0_real64]
  qs64=4.0_real64; ns64=5.0_real64; minmass=6.0_real64; maxmass=7.0_real64
  number_bounds(1,1,1)=8.0_real64; number_bounds(1,2,1)=9.0_real64
  prepared_q=10.0_real32; prepared_n=11.0_real32; mut_diff=1.0_real32
  xkmhd_diff=1.0_real32; msfux_diff=1.0_real32; msfuy_diff=1.0_real32
  msfvx_inv_diff=1.0_real32; msfvy_diff=1.0_real32; msftx=1.0_real32; msfty=1.0_real32
  pr87_later_qsrc=12.0_real64; pr87_later_nsrc=13.0_real64
  pr87_all_pair_diffusion_delta=14.0_real64; pr87_all_pair_diffusion_old=15.0_real64
  if (.not.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(1))) then
            IF (.NOT.prepared_donor_is_safe(source_sum64(1),source_sum64(2),drydensity(cell))) THEN
              ! Failed-call-only C11 capture. Recompute Dprepared for this exact pair/cell;
              ! the full-field workspace may currently belong to the other selected pair.
              CALL horizontal_diffusion64(prepared_q(:,:,:,p),mut_diff,c1,c2, &
                   msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
                   rdx,rdy,ims,ime,kms,kme,jms,jme,i,i,j,j,k,k,prepared_diffusion)
              CALL horizontal_diffusion64(prepared_n(:,:,:,p),mut_diff,c1,c2, &
                   msfux_diff,msfuy_diff,msfvx_inv_diff,msfvy_diff,msftx,msfty,xkmhd_diff, &
                   rdx,rdy,ims,ime,kms,kme,jms,jme,i,i,j,j,k,k,prepared_n_diffusion)
              stage_diag_qdiff=prepared_diffusion(i,k,j)
              stage_diag_ndiff=prepared_n_diffusion(i,k,j)
              OPEN(NEWUNIT=stage_diag_u,FILE='pr85_joint_source_failure.raw', &
                   STATUS='UNKNOWN',POSITION='APPEND')
              WRITE(stage_diag_u,'(a,1x,6(i10,1x),2(z16.16,1x))') 'VIRTUAL_DONOR_STAGE',itimestep,rk,p,i,j,k, &
                   TRANSFER(source_sum64(1),0_int64),TRANSFER(source_sum64(2),0_int64)
              WRITE(stage_diag_u,'(a,1x,6(z8.8,1x))') 'VDS_OPERANDS_R32', &
                   TRANSFER(qb(cell,p),0_int32),TRANSFER(nb(cell,p),0_int32), &
                   TRANSFER(oldcarrier(cell),0_int32),TRANSFER(newcarrier(cell),0_int32), &
                   TRANSFER(drydensity(cell),0_int32),TRANSFER(dt,0_int32)
              WRITE(stage_diag_u,'(a,1x,2(z16.16,1x))') 'VDS_OPERANDS_R64', &
                   TRANSFER(qs64(cell,p),0_int64),TRANSFER(ns64(cell,p),0_int64)
              WRITE(stage_diag_u,'(a,1x,12(z16.16,1x))') 'VDS_SOURCE_DIFFUSION', &
                   TRANSFER(pr87_later_qsrc(i,k,j,p),0_int64), &
                   TRANSFER(pr87_later_nsrc(i,k,j,p),0_int64), &
                   TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p-1),0_int64), &
                   TRANSFER(pr87_all_pair_diffusion_delta(i,k,j,2*p),0_int64), &
                   TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p-1),0_int64), &
                   TRANSFER(pr87_all_pair_diffusion_old(i,k,j,2*p),0_int64), &
                   TRANSFER(stage_diag_qdiff,0_int64),TRANSFER(stage_diag_ndiff,0_int64), &
                   TRANSFER(minmass(p),0_int64),TRANSFER(maxmass(p),0_int64), &
                   TRANSFER(number_bounds(cell,1,p),0_int64),TRANSFER(number_bounds(cell,2,p),0_int64)
              ! 3x3 prepared REAL32 stencil, same k; each row is dx=-1,0,+1 and dy.
              DO stage_diag_dy=-1,1
                WRITE(stage_diag_u,'(a,1x,3(i10,1x),3(z8.8,1x))') 'VDS_Q_STENCIL',itimestep,p,stage_diag_dy, &
                  (TRANSFER(prepared_q(i+stage_diag_dx,k,j+stage_diag_dy,p),0_int32), &
                   stage_diag_dx=-1,1)
                WRITE(stage_diag_u,'(a,1x,3(i10,1x),3(z8.8,1x))') 'VDS_N_STENCIL',itimestep,p,stage_diag_dy, &
                  (TRANSFER(prepared_n(i+stage_diag_dx,k,j+stage_diag_dy,p),0_int32), &
                   stage_diag_dx=-1,1)
              END DO
              WRITE(stage_diag_u,'(a,1x,3(z8.8,1x))') 'VDS_DIFFUSIVITY', &
                   TRANSFER(mut_diff(i,j),0_int32),TRANSFER(c1(k),0_int32),TRANSFER(c2(k),0_int32)
              DO stage_diag_dy=-1,1
                WRITE(stage_diag_u,'(a,1x,3(i10,1x),6(z8.8,1x))') 'VDS_GEOMETRY_X',itimestep,p,stage_diag_dy, &
                  (TRANSFER(xkmhd_diff(i+stage_diag_dx,k,j+stage_diag_dy),0_int32), &
                   stage_diag_dx=-1,1), &
                  (TRANSFER(mut_diff(i+stage_diag_dx,j+stage_diag_dy),0_int32),stage_diag_dx=-1,1)
              END DO
              WRITE(stage_diag_u,'(a,1x,10(z8.8,1x))') 'VDS_GEOMETRY_FACE', &
                   TRANSFER(msfux_diff(i,j),0_int32),TRANSFER(msfux_diff(i+1,j),0_int32), &
                   TRANSFER(msfuy_diff(i,j),0_int32),TRANSFER(msfuy_diff(i+1,j),0_int32), &
                   TRANSFER(msfvx_inv_diff(i,j-1),0_int32),TRANSFER(msfvx_inv_diff(i,j),0_int32), &
                   TRANSFER(msfvx_inv_diff(i,j+1),0_int32), &
                   TRANSFER(msfvy_diff(i,j),0_int32),TRANSFER(msfvy_diff(i,j+1),0_int32)
              WRITE(stage_diag_u,'(a,1x,6(z8.8,1x))') 'VDS_GEOMETRY_Y', &
                   TRANSFER(msfvy_diff(i,j-1),0_int32),TRANSFER(msfvy_diff(i,j),0_int32), &
                   TRANSFER(msfvy_diff(i,j+1),0_int32),TRANSFER(msftx(i,j),0_int32), &
                   TRANSFER(msfty(i,j),0_int32),TRANSFER(rdx,0_int32)
              WRITE(stage_diag_u,'(a,1x,z8.8,1x)') 'VDS_RDY',TRANSFER(rdy,0_int32)
              CLOSE(stage_diag_u)
              CALL wrf_error_fatal('PR87 unsafe complete source-prepared virtual donor')
            END IF
  endif
contains
  logical function prepared_donor_is_safe(q,n,rho)
    real(real64),intent(in)::q,n
    real(real32),intent(in)::rho
    prepared_donor_is_safe=.false.
  end function
  subroutine wrf_error_fatal(message)
    character(*),intent(in)::message
    print '(a)',trim(message)
  end subroutine
end program
