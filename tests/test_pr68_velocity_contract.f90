program test_pr68_velocity_contract
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none
  integer, parameter :: ilo=2, ihi=3, klo=4, khi=6
  double precision :: vt(ilo:ihi,klo:khi,4)
  double precision :: vtn(ilo:ihi,klo:khi,2)
  double precision :: mass_rate(ilo:ihi,klo:khi,4)
  double precision :: number_rate(ilo:ihi,klo:khi,2)
  double precision :: mass_rate_cm(ilo:ihi,klo:khi,4)
  double precision :: number_rate_cm(ilo:ihi,klo:khi,2)
  double precision :: vt_cm(ilo:ihi,klo:khi,4)
  double precision :: vtn_cm(ilo:ihi,klo:khi,2)
  double precision :: saved_vt(ilo:ihi,klo:khi,4)
  double precision :: saved_vtn(ilo:ihi,klo:khi,2)
  double precision :: zero_mass_moment(4), zero_number_moment(2)
  double precision :: mass_flux(4), number_flux(2)
  real :: delz(ilo-1:ihi+1,klo-1:khi+1)
  real :: delz_cm(ilo-1:ihi+1,klo-1:khi+1)
  integer :: i,k,minor

  interface
    subroutine kdm6_velocity_rates(vt,vtn,delz,mass_rate,number_rate,ims,ime,kms,kme,its,ite,kts,kte)
      integer, intent(in) :: ims,ime,kms,kme,its,ite,kts,kte
      double precision, intent(in) :: vt(its:ite,kts:kte,4)
      double precision, intent(in) :: vtn(its:ite,kts:kte,2)
      real, intent(in) :: delz(ims:ime,kms:kme)
      double precision, intent(out) :: mass_rate(its:ite,kts:kte,4)
      double precision, intent(out) :: number_rate(its:ite,kts:kte,2)
    end subroutine kdm6_velocity_rates
  end interface

  delz=-999.0
  do k=klo,khi
    do i=ilo,ihi
      delz(i,k)=10.0*real(k-3)+2.0*real(i-1)
      vt(i,k,1:4)=[0.8d0,0.25d0,0.4d0,0.12d0]*real(i+k)
      vtn(i,k,1:2)=[0.15d0,0.05d0]*real(2*i+k)
    enddo
  enddo
  saved_vt=vt
  saved_vtn=vtn
  call kdm6_velocity_rates(vt,vtn,delz,mass_rate,number_rate,ilo-1,ihi+1,klo-1,khi+1,ilo,ihi,klo,khi)
  call assert_rates('initial')
  call assert_unchanged('initial')

  ! A nonzero terminal speed does not create flux for absent mass/moments.
  zero_mass_moment=0.0d0
  zero_number_moment=0.0d0
  mass_flux=zero_mass_moment*mass_rate(ilo,klo,:)
  number_flux=zero_number_moment*number_rate(ilo,klo,:)
  if (any(mass_flux /= 0.0d0) .or. any(number_flux /= 0.0d0)) &
    error stop 'zero hydrometeor moments produced sedimentation flux'

  vt_cm=vt*100.0d0
  vtn_cm=vtn*100.0d0
  delz_cm=delz*100.0
  call kdm6_velocity_rates(vt_cm,vtn_cm,delz_cm,mass_rate_cm,number_rate_cm, &
                           ilo-1,ihi+1,klo-1,khi+1,ilo,ihi,klo,khi)
  if (maxval(abs(mass_rate_cm-mass_rate)) > &
        8.0d0*epsilon(1.0d0)*maxval(abs(mass_rate)) .or. &
      maxval(abs(number_rate_cm-number_rate)) > &
        8.0d0*epsilon(1.0d0)*maxval(abs(number_rate))) &
    error stop 'm/s and cm/s representations changed the rates'

  do minor=1,3
    vt=vt*0.5d0
    vtn=vtn*0.75d0
    saved_vt=vt
    saved_vtn=vtn
    call kdm6_velocity_rates(vt,vtn,delz,mass_rate,number_rate,ilo-1,ihi+1,klo-1,khi+1,ilo,ihi,klo,khi)
    call assert_rates('minor loop')
    call assert_unchanged('minor loop')
  enddo

  ! An exact zero-speed state remains zero through rate conversion.
  vt=0.0d0
  vtn=0.0d0
  call kdm6_velocity_rates(vt,vtn,delz,mass_rate,number_rate,ilo-1,ihi+1,klo-1,khi+1,ilo,ihi,klo,khi)
  if (any(mass_rate /= 0.0d0) .or. any(number_rate /= 0.0d0)) error stop 'zero velocity did not yield zero rate'
  if (.not. all(ieee_is_finite(mass_rate)) .or. .not. all(ieee_is_finite(number_rate))) &
    error stop 'zero velocity produced a non-finite rate'
  print '(a)', 'PR68 VELOCITY RATE CONTRACT PASS'

contains
  subroutine assert_rates(label)
    character(len=*), intent(in) :: label
    integer :: ii,kk,phase
    double precision :: expected
    do kk=klo,khi
      do ii=ilo,ihi
        do phase=1,4
          expected=vt(ii,kk,phase)/dble(delz(ii,kk))
          call assert_close(mass_rate(ii,kk,phase),expected,label//' mass rate')
        enddo
        do phase=1,2
          expected=vtn(ii,kk,phase)/dble(delz(ii,kk))
          call assert_close(number_rate(ii,kk,phase),expected,label//' number rate')
        enddo
      enddo
    enddo
    if (mass_rate(ilo,klo,1) == number_rate(ilo,klo,1)) &
      error stop 'mass and number rates were conflated'
  end subroutine assert_rates

  subroutine assert_unchanged(label)
    character(len=*), intent(in) :: label
    if (any(vt /= saved_vt) .or. any(vtn /= saved_vtn)) &
      error stop 'terminal velocities mutated during '//label
  end subroutine assert_unchanged

  subroutine assert_close(actual,expected,label)
    double precision, intent(in) :: actual,expected
    character(len=*), intent(in) :: label
    if (.not. ieee_is_finite(actual)) error stop label//' is non-finite'
    if (actual /= expected) error stop label//' mismatch'
  end subroutine assert_close
end program test_pr68_velocity_contract
