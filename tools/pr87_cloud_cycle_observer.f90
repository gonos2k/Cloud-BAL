! Read-only cloud-pair summaries at completed state boundaries.
subroutine pr87_cloud_cycle(label, step, ims, ime, jms, jme, kms, kme, &
                           its, ite, jts, jte, kts, kte, qc, nc)
  use, intrinsic :: iso_fortran_env, only: real64, int32
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  character(*), intent(in) :: label
  integer, intent(in) :: step, ims, ime, jms, jme, kms, kme
  integer, intent(in) :: its, ite, jts, jte, kts, kte
  real, intent(in) :: qc(ims:ime,kms:kme,jms:jme), nc(ims:ime,kms:kme,jms:jme)
  integer :: i, j, k, unit, status, nonfinite, negative, mass_only, number_only
  integer :: first(3), probe(3)
  character(80) :: text
  real(real64) :: first_q, first_n

  nonfinite=0; negative=0; mass_only=0; number_only=0
  first=0; first_q=0; first_n=0
  do j=jts,jte
    do i=its,ite
      do k=kts,kte
        if (.not.ieee_is_finite(qc(i,k,j)) .or. .not.ieee_is_finite(nc(i,k,j))) then
          nonfinite=nonfinite+1
          cycle
        endif
        if (qc(i,k,j)<0 .or. nc(i,k,j)<0) negative=negative+1
        if (qc(i,k,j)>0 .and. nc(i,k,j)==0) mass_only=mass_only+1
        if (qc(i,k,j)==0 .and. nc(i,k,j)>0) number_only=number_only+1
        if (all(first==0)) then
          if ((qc(i,k,j)>0 .and. nc(i,k,j)==0) .or. &
              (qc(i,k,j)==0 .and. nc(i,k,j)>0)) then
            first=(/i,j,k/)
            first_q=real(qc(i,k,j),real64); first_n=real(nc(i,k,j),real64)
          endif
        endif
      enddo
    enddo
  enddo
  open(newunit=unit,file='pr87_cloud_cycle.log',status='unknown',position='append',iostat=status)
  if (status/=0) error stop 'PR87 cycle log open failed'
  write(unit,'(a,1x,a,11(1x,i0),2(1x,es24.16))') 'PR87_CLOUD',trim(label), &
       step,its,ite,jts,jte,kts,kte,nonfinite,negative,mass_only,number_only,first_q,first_n
  write(unit,'(a,1x,a,4(1x,i0),2(1x,es24.16))') 'PR87_FIRST',trim(label), &
       step,first,first_q,first_n
  call get_environment_variable('PR87_PROBE',text,status=status)
  if (status==0) then
    read(text,*,iostat=status) probe
    if (status/=0) error stop 'PR87 invalid probe coordinates'
    i=probe(1); j=probe(2); k=probe(3)
    if (i>=its .and. i<=ite .and. j>=jts .and. j<=jte .and. k>=kts .and. k<=kte) then
      write(unit,'(a,1x,a,4(1x,i0),2(1x,es24.16),2(1x,z8.8))') &
           'PR87_PROBE',trim(label),step,probe,real(qc(i,k,j),real64),real(nc(i,k,j),real64), &
           transfer(qc(i,k,j),0_int32),transfer(nc(i,k,j),0_int32)
    endif
  endif
  close(unit,iostat=status)
  if (status/=0) error stop 'PR87 cycle log close failed'
end subroutine pr87_cloud_cycle
