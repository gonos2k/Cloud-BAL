subroutine pr87_qn_density_store(itimestep,rk_step,ims,ime,kms,kme,jms,jme, &
     its,ite,jts,jte,kts,kte,al,alb,qcloud,ncloud,qrain,nrain, &
     cloud_pidn,cloud_power,cloud_lambda_min,cloud_lambda_max, &
     rain_pidn,rain_power,rain_lambda_min,rain_lambda_max,valid)
  use iso_fortran_env, only: real32,real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, intent(in) :: itimestep,rk_step,ims,ime,kms,kme,jms,jme
  integer, intent(in) :: its,ite,jts,jte,kts,kte
  real(real32), intent(in) :: al(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: alb(ims:ime,kms:kme,jms:jme)
  real(real32), intent(inout) :: qcloud(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: ncloud(ims:ime,kms:kme,jms:jme)
  real(real32), intent(inout) :: qrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: nrain(ims:ime,kms:kme,jms:jme)
  real(real32), intent(in) :: cloud_pidn,cloud_power,cloud_lambda_min,cloud_lambda_max
  real(real32), intent(in) :: rain_pidn,rain_power,rain_lambda_min,rain_lambda_max
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

  character(len=*), parameter :: ledger_name='pr87_qn_density_storage.raw'
  real(real32), allocatable :: qcloud_candidate(:,:,:),qrain_candidate(:,:,:)
  real(real32), allocatable :: rho_values(:,:,:),ncloud_volume(:,:,:),nrain_volume(:,:,:)
  real(real64), allocatable :: dqcloud(:,:,:),dqrain(:,:,:)
  real(real64), allocatable :: dncloud_volume(:,:,:),dnrain_volume(:,:,:)
  real(real32) :: rho,q_stored,n_volume_stored
  real(real64) :: sum_dqc,l1_dqc,max_dqc,sum_dqr,l1_dqr,max_dqr
  real(real64) :: sum_dncvol,l1_dncvol,max_dncvol,sum_dnrvol,l1_dnrvol,max_dnrvol
  integer :: i,j,k,io_status,ledger_unit,processed,alloc_status,failure_stage
  integer :: qcloud_changed,qrain_changed,ncloud_rounding,nrain_rounding
  integer :: cloud_adjustment,rain_adjustment
  integer(kind=8) :: ledger_size
  logical :: density_valid,cell_valid,ledger_exists

  valid=.false.
  if (itimestep<1 .or. rk_step<1 .or. rk_step>3) return
  if (ims>ime .or. kms>kme .or. jms>jme .or. its<ims .or. ite>ime .or. &
      kts<kms .or. kte>kme .or. jts<jms .or. jte>jme .or. &
      its>ite .or. kts>kte .or. jts>jte) return
  if (.not.all(ieee_is_finite([cloud_pidn,cloud_power,cloud_lambda_min, &
      cloud_lambda_max,rain_pidn,rain_power,rain_lambda_min,rain_lambda_max]))) return

  allocate(qcloud_candidate(its:ite,kts:kte,jts:jte), &
           qrain_candidate(its:ite,kts:kte,jts:jte), &
           rho_values(its:ite,kts:kte,jts:jte), &
           ncloud_volume(its:ite,kts:kte,jts:jte), &
           nrain_volume(its:ite,kts:kte,jts:jte), &
           dqcloud(its:ite,kts:kte,jts:jte),dqrain(its:ite,kts:kte,jts:jte), &
           dncloud_volume(its:ite,kts:kte,jts:jte), &
           dnrain_volume(its:ite,kts:kte,jts:jte),stat=alloc_status)
  if (alloc_status/=0) then
    if (allocated(qcloud_candidate)) deallocate(qcloud_candidate)
    if (allocated(qrain_candidate)) deallocate(qrain_candidate)
    if (allocated(rho_values)) deallocate(rho_values)
    if (allocated(ncloud_volume)) deallocate(ncloud_volume)
    if (allocated(nrain_volume)) deallocate(nrain_volume)
    if (allocated(dqcloud)) deallocate(dqcloud)
    if (allocated(dqrain)) deallocate(dqrain)
    if (allocated(dncloud_volume)) deallocate(dncloud_volume)
    if (allocated(dnrain_volume)) deallocate(dnrain_volume)
    return
  end if

  sum_dqc=0.0_real64; l1_dqc=0.0_real64; max_dqc=0.0_real64
  sum_dqr=0.0_real64; l1_dqr=0.0_real64; max_dqr=0.0_real64
  sum_dncvol=0.0_real64; l1_dncvol=0.0_real64; max_dncvol=0.0_real64
  sum_dnrvol=0.0_real64; l1_dnrvol=0.0_real64; max_dnrvol=0.0_real64
  processed=0; qcloud_changed=0; qrain_changed=0
  ncloud_rounding=0; nrain_rounding=0

  ! Stage and validate both species for every tile cell before writing or commit.
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        rho=0.0_real32
        call pr85_dry_density_from_al_alb(al(i,k,j),alb(i,k,j),rho,density_valid)
        if (.not.density_valid) then
          failure_stage=1
          write(*,*) 'PR87_QN_DENSITY_REJECT',itimestep,rk_step,1,i,j,k, &
               failure_stage,qcloud(i,k,j),ncloud(i,k,j),qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if

        call pr87_number_volume_store(qcloud(i,k,j),ncloud(i,k,j),rho, &
             cloud_pidn,cloud_power,cloud_lambda_min,cloud_lambda_max, &
             q_stored,n_volume_stored,cell_valid,dqcloud(i,k,j), &
             dncloud_volume(i,k,j),cloud_adjustment)
        if (.not.cell_valid .or. .not.ieee_is_finite(q_stored) .or. &
            .not.ieee_is_finite(n_volume_stored) .or. &
            .not.ieee_is_finite(dqcloud(i,k,j)) .or. &
            .not.ieee_is_finite(dncloud_volume(i,k,j))) then
          failure_stage=2
          write(*,*) 'PR87_QN_DENSITY_REJECT',itimestep,rk_step,1,i,j,k, &
               failure_stage,qcloud(i,k,j),ncloud(i,k,j),qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        qcloud_candidate(i,k,j)=q_stored
        ncloud_volume(i,k,j)=n_volume_stored

        call pr87_number_volume_store(qrain(i,k,j),nrain(i,k,j),rho, &
             rain_pidn,rain_power,rain_lambda_min,rain_lambda_max, &
             q_stored,n_volume_stored,cell_valid,dqrain(i,k,j), &
             dnrain_volume(i,k,j),rain_adjustment)
        if (.not.cell_valid .or. .not.ieee_is_finite(q_stored) .or. &
            .not.ieee_is_finite(n_volume_stored) .or. &
            .not.ieee_is_finite(dqrain(i,k,j)) .or. &
            .not.ieee_is_finite(dnrain_volume(i,k,j))) then
          failure_stage=3
          write(*,*) 'PR87_QN_DENSITY_REJECT',itimestep,rk_step,2,i,j,k, &
               failure_stage,qcloud(i,k,j),ncloud(i,k,j),qrain(i,k,j),nrain(i,k,j),rho
          goto 900
        end if
        qrain_candidate(i,k,j)=q_stored
        nrain_volume(i,k,j)=n_volume_stored
        rho_values(i,k,j)=rho

        processed=processed+1
        sum_dqc=sum_dqc+dqcloud(i,k,j); l1_dqc=l1_dqc+abs(dqcloud(i,k,j))
        max_dqc=max(max_dqc,abs(dqcloud(i,k,j)))
        sum_dqr=sum_dqr+dqrain(i,k,j); l1_dqr=l1_dqr+abs(dqrain(i,k,j))
        max_dqr=max(max_dqr,abs(dqrain(i,k,j)))
        sum_dncvol=sum_dncvol+dncloud_volume(i,k,j)
        l1_dncvol=l1_dncvol+abs(dncloud_volume(i,k,j))
        max_dncvol=max(max_dncvol,abs(dncloud_volume(i,k,j)))
        sum_dnrvol=sum_dnrvol+dnrain_volume(i,k,j)
        l1_dnrvol=l1_dnrvol+abs(dnrain_volume(i,k,j))
        max_dnrvol=max(max_dnrvol,abs(dnrain_volume(i,k,j)))
        if (dqcloud(i,k,j)/=0.0_real64) qcloud_changed=qcloud_changed+1
        if (dqrain(i,k,j)/=0.0_real64) qrain_changed=qrain_changed+1
        if (dncloud_volume(i,k,j)/=0.0_real64) ncloud_rounding=ncloud_rounding+1
        if (dnrain_volume(i,k,j)/=0.0_real64) nrain_rounding=nrain_rounding+1
      end do
    end do
  end do

  inquire(file=ledger_name,exist=ledger_exists,size=ledger_size,iostat=io_status)
  if (io_status/=0) then
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,1,io_status
    goto 900
  end if
  open(newunit=ledger_unit,file=ledger_name,status='unknown',position='append', &
       action='write',iostat=io_status)
  if (io_status/=0) then
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,2,io_status
    goto 900
  end if
  if (.not.ledger_exists .or. ledger_size==0_8) then
    write(ledger_unit,'(a)',iostat=io_status) &
      '# PR87_QN_DENSITY_CELL time,rk,species_id,i,j,k,rho[kg/m3],Qbefore[kg/kg],Qafter[kg/kg],'// &
      'Nspecific[number/kg],Nvolume_predicted[number/m3],dQ_specific[kg/kg],dNvolume_predicted[number/m3]; '// &
      'prospective Nvolume is ordinary R32 conversion, not committed N.'
    if (io_status/=0) then
      close(ledger_unit)
      write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,3,io_status
      goto 900
    end if
    write(ledger_unit,'(a)',iostat=io_status) &
      '# PR87_QN_DENSITY_SUM time,rk,i0,i1,j0,j1,k0,k1,cells,Qcloud_changed,Qrain_changed,'// &
      'Ncloud_volume_rounding_nonzero,Nrain_volume_rounding_nonzero,'// &
      'sum_dQcloud,L1_dQcloud,max_abs_dQcloud,sum_dQrain,L1_dQrain,max_abs_dQrain,'// &
      'sum_prospective_dNcloudvol,L1_prospective_dNcloudvol,max_abs_prospective_dNcloudvol,'// &
      'sum_prospective_dNrainvol,L1_prospective_dNrainvol,max_abs_prospective_dNrainvol; '// &
      'unweighted diagnostics; prospective Nvolume deltas are not committed or conserved totals.'
    if (io_status/=0) then
      close(ledger_unit)
      write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,4,io_status
      goto 900
    end if
  end if

  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        if (dqcloud(i,k,j)/=0.0_real64) then
          write(ledger_unit,'(a,6i10,1p,7e24.16)',iostat=io_status) &
            'PR87_QN_DENSITY_CELL',itimestep,rk_step,1,i,j,k, &
            real(rho_values(i,k,j),real64),real(qcloud(i,k,j),real64), &
            real(qcloud_candidate(i,k,j),real64),real(ncloud(i,k,j),real64), &
            real(ncloud_volume(i,k,j),real64),dqcloud(i,k,j),dncloud_volume(i,k,j)
          if (io_status/=0) then
            close(ledger_unit)
            write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,5,io_status
            goto 900
          end if
        end if
        if (dqrain(i,k,j)/=0.0_real64) then
          write(ledger_unit,'(a,6i10,1p,7e24.16)',iostat=io_status) &
            'PR87_QN_DENSITY_CELL',itimestep,rk_step,2,i,j,k, &
            real(rho_values(i,k,j),real64),real(qrain(i,k,j),real64), &
            real(qrain_candidate(i,k,j),real64),real(nrain(i,k,j),real64), &
            real(nrain_volume(i,k,j),real64),dqrain(i,k,j),dnrain_volume(i,k,j)
          if (io_status/=0) then
            close(ledger_unit)
            write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,6,io_status
            goto 900
          end if
        end if
      end do
    end do
  end do
  write(ledger_unit,'(a,13i10,1p,12e24.16)',iostat=io_status) &
    'PR87_QN_DENSITY_SUM',itimestep,rk_step,its,ite,jts,jte,kts,kte,processed, &
    qcloud_changed,qrain_changed,ncloud_rounding,nrain_rounding, &
    sum_dqc,l1_dqc,max_dqc,sum_dqr,l1_dqr,max_dqr, &
    sum_dncvol,l1_dncvol,max_dncvol,sum_dnrvol,l1_dnrvol,max_dnrvol
  if (io_status/=0) then
    close(ledger_unit)
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,7,io_status
    goto 900
  end if
  close(ledger_unit,iostat=io_status)
  if (io_status/=0) then
    write(*,*) 'PR87_QN_DENSITY_IO_REJECT',itimestep,rk_step,8,io_status
    goto 900
  end if

  ! The tile commit is the only mutation point; both Q species move together.
  do j=jts,jte
    do k=kts,kte
      do i=its,ite
        qcloud(i,k,j)=qcloud_candidate(i,k,j)
        qrain(i,k,j)=qrain_candidate(i,k,j)
      end do
    end do
  end do
  valid=.true.
900 continue
  deallocate(qcloud_candidate,qrain_candidate,rho_values,ncloud_volume,nrain_volume, &
             dqcloud,dqrain,dncloud_volume,dnrain_volume)
end subroutine pr87_qn_density_store
