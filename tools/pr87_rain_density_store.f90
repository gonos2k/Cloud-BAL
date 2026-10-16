subroutine pr87_rain_density_store(itimestep,rk_step,ims,ime,kms,kme,jms,jme, &
     its,ite,jts,jte,kts,kte,al,alb,qrain,nrain,pidnr,power,lambda_min,lambda_max,valid)
  use iso_fortran_env, only: real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, intent(in) :: itimestep,rk_step,ims,ime,kms,kme,jms,jme
  integer, intent(in) :: its,ite,jts,jte,kts,kte
  real(real32), intent(in) :: al(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: alb(ims:ime,kms:kme,jms:jme)
  real(real32), intent(inout) :: qrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: nrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: pidnr,power,lambda_min,lambda_max
  logical, intent(out) :: valid
  interface
    subroutine pr85_dry_density_from_al_alb(al,alb,dry_density,valid)
      use iso_fortran_env, only: real32
      real, intent(in) :: al,alb
      real(real32), intent(out) :: dry_density
      logical, intent(out) :: valid
    end subroutine pr85_dry_density_from_al_alb
    subroutine pr87_number_volume_store(q_specific,n_specific,dry_density,pidnr,power, &
         lambda_min,lambda_max,q_stored,n_volume,valid,delta_q,delta_nvolume,adjustment)
      use iso_fortran_env, only: real32,real64
      real(real32), intent(in) :: q_specific,n_specific,dry_density,pidnr,power
      real(real32), intent(in) :: lambda_min,lambda_max
      real(real32), intent(out) :: q_stored,n_volume
      logical, intent(out) :: valid
      real(real64), intent(out) :: delta_q,delta_nvolume
      integer, intent(out) :: adjustment
    end subroutine pr87_number_volume_store
  end interface

  character(len=*), parameter :: ledger_name='pr87_rain_density_storage.raw'
  real(real32), allocatable :: q_candidate(:,:,:),rho_values(:,:,:),n_volume(:,:,:)
  real(real64), allocatable :: delta_q(:,:,:),delta_nvolume(:,:,:)
  real(real32) :: rho,q_stored,n_volume_stored
  real(real64) :: sum_delta_q,l1_delta_q,max_delta_q
  real(real64) :: sum_delta_nvolume,l1_delta_nvolume,max_delta_nvolume
  integer :: i,j,k,io_status,ledger_unit,processed,q_changed,nvolume_rounded
  integer :: failure_stage
  integer :: adjustment
  integer(kind=8) :: ledger_size
  logical :: density_valid,cell_valid,ledger_exists

  valid=.false.
  if (itimestep<1 .or. rk_step<1 .or. rk_step>3) return
  if (ims>ime .or. kms>kme .or. jms>jme .or. its<ims .or. ite>ime .or. &
      kts<kms .or. kte>kme .or. jts<jms .or. jte>jme .or. &
      its>ite .or. kts>kte .or. jts>jte) return
  if (.not.all(ieee_is_finite([pidnr,power,lambda_min,lambda_max]))) return
  if (pidnr<=0.0_real32 .or. power<=0.0_real32 .or. power>8.0_real32 .or. &
      lambda_min<=0.0_real32 .or. lambda_max<lambda_min) return

  allocate(q_candidate(its:ite,kts:kte,jts:jte), &
           rho_values(its:ite,kts:kte,jts:jte), &
           n_volume(its:ite,kts:kte,jts:jte), &
           delta_q(its:ite,kts:kte,jts:jte), &
           delta_nvolume(its:ite,kts:kte,jts:jte))
  sum_delta_q=0.0_real64; l1_delta_q=0.0_real64; max_delta_q=0.0_real64
  sum_delta_nvolume=0.0_real64; l1_delta_nvolume=0.0_real64; max_delta_nvolume=0.0_real64
  processed=0; q_changed=0; nvolume_rounded=0

  ! Validate every cell and stage all Q changes before touching model state.
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        rho=0.0_real32
        call pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j),rho,density_valid)
        if (.not.density_valid) then
          failure_stage=1
          write(*,*) 'PR87_RAIN_DENSITY_REJECT',itimestep,rk_step,i,j,k, &
               failure_stage,qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        call pr87_number_volume_store(qrain(i,k,j),nrain(i,k,j),rho,pidnr,power, &
             lambda_min,lambda_max,q_stored,n_volume_stored,cell_valid, &
             delta_q(i,k,j),delta_nvolume(i,k,j),adjustment)
        if (.not.cell_valid) then
          failure_stage=2
          write(*,*) 'PR87_RAIN_DENSITY_REJECT',itimestep,rk_step,i,j,k, &
               failure_stage,qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        if (.not.ieee_is_finite(delta_q(i,k,j)) .or. &
            .not.ieee_is_finite(delta_nvolume(i,k,j)) .or. &
            .not.ieee_is_finite(q_stored) .or. .not.ieee_is_finite(n_volume_stored)) then
          failure_stage=3
          write(*,*) 'PR87_RAIN_DENSITY_REJECT',itimestep,rk_step,i,j,k, &
               failure_stage,qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        q_candidate(i,k,j)=q_stored
        rho_values(i,k,j)=rho
        n_volume(i,k,j)=n_volume_stored
        processed=processed+1
        sum_delta_q=sum_delta_q+delta_q(i,k,j)
        l1_delta_q=l1_delta_q+abs(delta_q(i,k,j))
        max_delta_q=max(max_delta_q,abs(delta_q(i,k,j)))
        sum_delta_nvolume=sum_delta_nvolume+delta_nvolume(i,k,j)
        l1_delta_nvolume=l1_delta_nvolume+abs(delta_nvolume(i,k,j))
        max_delta_nvolume=max(max_delta_nvolume,abs(delta_nvolume(i,k,j)))
        if (delta_q(i,k,j)/=0.0_real64) q_changed=q_changed+1
        if (delta_nvolume(i,k,j)/=0.0_real64) nvolume_rounded=nvolume_rounded+1
      end do
    end do
  end do

  inquire(file=ledger_name,exist=ledger_exists,size=ledger_size,iostat=io_status)
  if (io_status/=0) goto 900
  open(newunit=ledger_unit,file=ledger_name,status='unknown',position='append', &
       action='write',iostat=io_status)
  if (io_status/=0) goto 900
  if (.not.ledger_exists .or. ledger_size==0_8) then
    write(ledger_unit,'(a)',iostat=io_status) &
      '# PR87_RAIN_DENSITY_SUM time,rk,i0,i1,j0,j1,k0,k1,cells,Q_changed,prospective_Nvol_rounding_nonzero,'// &
      'sum_delta_Q_specific,L1_delta_Q_specific,max_abs_delta_Q_specific,'// &
      'sum_prospective_delta_Nvolume,L1_prospective_delta_Nvolume,max_abs_prospective_delta_Nvolume; '// &
      'N_specific and AL/ALB are unchanged; Nvolume deltas are predicted ordinary REAL32 conversion rounding, '// &
      'not committed N or spatially/area/time weighted totals. Sparse CELL rows report actual Q changes only.'
    if (io_status/=0) then
      close(ledger_unit)
      goto 900
    end if
  end if
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        if (delta_q(i,k,j)/=0.0_real64) then
          write(ledger_unit,'(a,5i10,1p,7e24.16)',iostat=io_status) &
            'PR87_RAIN_DENSITY_CELL',itimestep,rk_step,i,j,k, &
            real(rho_values(i,k,j),real64),real(qrain(i,k,j),real64), &
            real(q_candidate(i,k,j),real64),real(nrain(i,k,j),real64), &
            real(n_volume(i,k,j),real64),delta_q(i,k,j),delta_nvolume(i,k,j)
          if (io_status/=0) then
            close(ledger_unit)
            goto 900
          end if
        end if
      end do
    end do
  end do
  write(ledger_unit,'(a,11i10,1p,6e24.16)',iostat=io_status) &
    'PR87_RAIN_DENSITY_SUM',itimestep,rk_step,its,ite,jts,jte,kts,kte, &
    processed,q_changed,nvolume_rounded,sum_delta_q,l1_delta_q,max_delta_q, &
    sum_delta_nvolume,l1_delta_nvolume,max_delta_nvolume
  if (io_status/=0) then
    close(ledger_unit)
    goto 900
  end if
  close(ledger_unit,iostat=io_status)
  if (io_status/=0) goto 900

  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        qrain(i,k,j)=q_candidate(i,k,j)
      end do
    end do
  end do
  valid=.true.
900 continue
  deallocate(q_candidate,rho_values,n_volume,delta_q,delta_nvolume)
end subroutine pr87_rain_density_store
