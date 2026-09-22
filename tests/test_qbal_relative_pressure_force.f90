program test_qbal_relative_pressure_force
  use, intrinsic :: iso_fortran_env, only: real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_nan, ieee_quiet_nan, &
                                           ieee_value
  use qbal_relative_pressure_force, only: build_relative_geopotential, &
                                          triangle_pressure_force
  implicit none

  integer :: failures

  failures=0
  call test_affine_gradient_and_metric(failures)
  call test_gauge_shift_changes_force(failures)
  call test_translation_and_reversal(failures)
  call test_relative_anchor_signs(failures)
  call test_gaps_and_isolated_reference(failures)
  call test_unknown_reference(failures)
  call test_nan_and_degenerate_failures(failures)

  if (failures/=0) then
    print '(a,i0)', 'Relative pressure-force tests failed: ',failures
    error stop 1
  end if
  print '(a)', 'Relative pressure-force tests passed'

contains

  subroutine check(condition,message,failures)
    logical, intent(in) :: condition
    character(len=*), intent(in) :: message
    integer, intent(inout) :: failures
    if (.not.condition) then
      failures=failures+1
      print '(a)', 'FAIL: '//trim(message)
    end if
  end subroutine check

  subroutine close_scalar(actual,expected,tolerance,message,failures)
    real(real64), intent(in) :: actual,expected,tolerance
    character(len=*), intent(in) :: message
    integer, intent(inout) :: failures
    call check(abs(actual-expected)<=tolerance*max(1.0_real64,abs(expected)), &
               message,failures)
  end subroutine close_scalar

  subroutine close_vector(actual,expected,tolerance,message,failures)
    real(real64), intent(in) :: actual(:),expected(:),tolerance
    character(len=*), intent(in) :: message
    integer, intent(inout) :: failures
    call check(size(actual)==size(expected) .and. &
               all(abs(actual-expected)<=tolerance*max(1.0_real64,abs(expected))), &
               message,failures)
  end subroutine close_vector

  subroutine check_nan_vector(values,message,failures)
    real(real64), intent(in) :: values(:)
    character(len=*), intent(in) :: message
    integer, intent(inout) :: failures
    call check(all(ieee_is_nan(values)),message,failures)
  end subroutine check_nan_vector

  subroutine test_affine_gradient_and_metric(failures)
    integer, intent(inout) :: failures
    real(real64) :: xy(2,3),phi(3),gradient(2),acceleration(2)
    real(real64) :: expected_gradient(2),expected_acceleration(2)
    real(real64) :: latitude,latitude0
    logical :: ok

    xy(:,1)=[0.0_real64,0.0_real64]
    xy(:,2)=[2.0_real64,0.0_real64]
    xy(:,3)=[0.0_real64,3.0_real64]
    phi=[7.0_real64,15.0_real64,1.0_real64]
    latitude=0.50_real64
    latitude0=0.20_real64
    call triangle_pressure_force(xy,phi,latitude,latitude0,gradient,acceleration,ok)
    expected_gradient=[4.0_real64,-2.0_real64]
    expected_acceleration=[-cos(latitude0)/cos(latitude)*4.0_real64, &
                           -cos(latitude)/cos(latitude0)*(-2.0_real64)]
    call check(ok,'affine pressure-surface triangle accepted',failures)
    call close_vector(gradient,expected_gradient,2.0e-14_real64, &
                      'affine scalar gradient',failures)
    call close_vector(acceleration,expected_acceleration,2.0e-14_real64, &
                      'east/north metric acceleration at explicit latitude',failures)
  end subroutine test_affine_gradient_and_metric

  subroutine test_gauge_shift_changes_force(failures)
    integer, intent(inout) :: failures
    real(real64) :: xy(2,3),phi(3),shifted(3),gradient(2),shifted_gradient(2)
    real(real64) :: acceleration(2),shifted_acceleration(2)
    logical :: ok,shifted_ok

    xy(:,1)=[100.0_real64,200.0_real64]
    xy(:,2)=[103.0_real64,200.0_real64]
    xy(:,3)=[100.0_real64,204.0_real64]
    phi=[30.0_real64,36.0_real64,22.0_real64]
    ! A column-dependent reference c(x,y) is constant through the vertical
    ! column, so it leaves layer thickness unchanged while changing horizontal
    ! force.  Its affine part is [0.75*x-0.50*y].
    shifted=phi+5.0_real64+0.75_real64*xy(1,:)-0.50_real64*xy(2,:)
    call triangle_pressure_force(xy,phi,0.40_real64,0.10_real64, &
                                gradient,acceleration,ok)
    call triangle_pressure_force(xy,shifted,0.40_real64,0.10_real64, &
                                shifted_gradient,shifted_acceleration,shifted_ok)
    call check(ok .and. shifted_ok,'reference gauge triangles accepted',failures)
    call close_vector(shifted_gradient-gradient,[0.75_real64,-0.50_real64], &
                      2.0e-14_real64,'reference gauge leaves thickness but changes gradient',failures)
    call check(any(abs(shifted_acceleration-acceleration)>1.0e-12_real64), &
               'reference gauge changes physical acceleration',failures)
  end subroutine test_gauge_shift_changes_force

  subroutine test_translation_and_reversal(failures)
    integer, intent(inout) :: failures
    real(real64) :: xy(2,3),translated(2,3),reversed(2,3)
    real(real64) :: phi(3),reversed_phi(3),gradient(2),translated_gradient(2)
    real(real64) :: reversed_gradient(2),acceleration(2),work(2)
    logical :: ok,translated_ok,reversed_ok

    xy(:,1)=[-4.0_real64,1.0_real64]
    xy(:,2)=[2.0_real64,5.0_real64]
    xy(:,3)=[1.0_real64,-3.0_real64]
    phi=11.0_real64+2.25_real64*xy(1,:)-1.50_real64*xy(2,:)
    translated=xy+spread([900000.0_real64,-700000.0_real64],2,3)
    reversed(:,1)=xy(:,1); reversed(:,2)=xy(:,3); reversed(:,3)=xy(:,2)
    reversed_phi=[phi(1),phi(3),phi(2)]
    call triangle_pressure_force(xy,phi,0.30_real64,0.25_real64, &
                                gradient,acceleration,ok)
    call triangle_pressure_force(translated,phi,0.30_real64,0.25_real64, &
                                translated_gradient,work,translated_ok)
    call triangle_pressure_force(reversed,reversed_phi,0.30_real64,0.25_real64, &
                                reversed_gradient,work,reversed_ok)
    call check(ok .and. translated_ok .and. reversed_ok, &
               'translated and reversed triangles accepted',failures)
    call close_vector(translated_gradient,gradient,2.0e-14_real64, &
                      'triangle translation preserves gradient',failures)
    call close_vector(reversed_gradient,gradient,2.0e-14_real64, &
                      'triangle vertex reversal preserves gradient',failures)
  end subroutine test_translation_and_reversal

  subroutine test_relative_anchor_signs(failures)
    integer, intent(inout) :: failures
    integer, parameter :: nlevel=5
    real(real64) :: delta_z(3,nlevel-1),delta_phi(3,nlevel)
    real(real64) :: expected(3,nlevel)
    logical :: level_valid(nlevel),layer_supported(nlevel-1),reachable(nlevel),ok
    integer :: k

    delta_z=0.0_real64
    do k=1,nlevel-1
      delta_z(:,k)=[real(k,real64),2.0_real64*real(k,real64), &
                    -0.5_real64*real(k,real64)]
    end do
    level_valid=.true.; layer_supported=.true.
    call build_relative_geopotential(delta_z,level_valid,layer_supported,3, &
                                     delta_phi,reachable,ok)
    expected=0.0_real64
    expected(:,1)=-9.80665_real64*delta_z(:,1)-9.80665_real64*delta_z(:,2)
    expected(:,2)=-9.80665_real64*delta_z(:,2)
    expected(:,3)=0.0_real64
    expected(:,4)=9.80665_real64*delta_z(:,3)
    expected(:,5)=9.80665_real64*(delta_z(:,3)+delta_z(:,4))
    call check(ok .and. all(reachable),'relative anchor column accepted',failures)
    call close_vector(reshape(delta_phi,[size(delta_phi)]), &
                      reshape(expected,[size(expected)]),2.0e-14_real64, &
                      'below/above reference signs',failures)
  end subroutine test_relative_anchor_signs

  subroutine test_gaps_and_isolated_reference(failures)
    integer, intent(inout) :: failures
    real(real64) :: delta_z(3,4),delta_phi(3,5)
    logical :: level_valid(5),layer_supported(4),reachable(5),ok

    delta_z=1.0_real64
    level_valid=.true.; layer_supported=.true.
    layer_supported(2)=.false.
    call build_relative_geopotential(delta_z,level_valid,layer_supported,3, &
                                     delta_phi,reachable,ok)
    call check(ok .and. reachable(3) .and. reachable(4) .and. reachable(5) .and. &
               .not.reachable(1) .and. .not.reachable(2), &
               'gap stops propagation without bridge',failures)
    call check(all(ieee_is_nan(delta_phi(:,1))) .and. &
               all(ieee_is_nan(delta_phi(:,2))), &
               'levels across unsupported gap remain NaN',failures)

    level_valid=.false.; level_valid(3)=.true.; layer_supported=.false.
    call build_relative_geopotential(delta_z,level_valid,layer_supported,3, &
                                     delta_phi,reachable,ok)
    call check(ok .and. reachable(3) .and. count(reachable)==1, &
               'isolated valid reference is allowed',failures)
    call check(delta_phi(1,3)==0.0_real64 .and. delta_phi(2,3)==0.0_real64 .and. &
               delta_phi(3,3)==0.0_real64,'isolated gauge is exactly zero',failures)
    level_valid=.true.; level_valid(4)=.false.; layer_supported=.true.
    call build_relative_geopotential(delta_z,level_valid,layer_supported,3, &
                                     delta_phi,reachable,ok)
    call check(.not.ok .and. .not.any(reachable), &
               'supported layer with invalid endpoint is rejected',failures)
    call check(all(ieee_is_nan(reshape(delta_phi,[size(delta_phi)]))), &
               'invalid support declaration returns all NaN',failures)

    level_valid=.true.; level_valid(2)=.false.; layer_supported=.false.
    call build_relative_geopotential(delta_z,level_valid,layer_supported,2, &
                                     delta_phi,reachable,ok)
    call check(.not.ok .and. .not.any(reachable), &
               'unsupported reference level is rejected',failures)
    call check(all(ieee_is_nan(reshape(delta_phi,[size(delta_phi)]))), &
               'unsupported reference leaves every output NaN',failures)
  end subroutine test_gaps_and_isolated_reference

  subroutine test_unknown_reference(failures)
    integer, intent(inout) :: failures
    real(real64) :: delta_z(3,2),delta_phi(3,3)
    logical :: level_valid(3),layer_supported(2),reachable(3),ok

    delta_z=1.0_real64; level_valid=.true.; layer_supported=.true.
    call build_relative_geopotential(delta_z,level_valid,layer_supported,0, &
                                     delta_phi,reachable,ok)
    call check(.not.ok .and. .not.any(reachable),'unknown reference is rejected',failures)
    call check_nan_vector(reshape(delta_phi,[size(delta_phi)]), &
                          'unknown reference leaves all outputs NaN',failures)
  end subroutine test_unknown_reference

  subroutine test_nan_and_degenerate_failures(failures)
    integer, intent(inout) :: failures
    real(real64) :: delta_z(3,2),delta_phi(3,3),before(3,3)
    real(real64) :: xy(2,3),bad_xy(2,3),phi(3),gradient(2),acceleration(2),nan
    logical :: level_valid(3),layer_supported(2),reachable(3),ok

    nan=ieee_value(0.0_real64,ieee_quiet_nan)
    delta_z=1.0_real64; level_valid=.true.; layer_supported=.true.
    delta_z(2,1)=nan
    before=42.0_real64
    delta_phi=before
    call build_relative_geopotential(delta_z,level_valid,layer_supported,2, &
                                     delta_phi,reachable,ok)
    call check(.not.ok .and. .not.any(reachable), &
               'nonfinite supported thickness fails transactionally',failures)
    call check_nan_vector(reshape(delta_phi,[size(delta_phi)]), &
                          'nonfinite thickness returns all NaN',failures)

    xy(:,1)=[0.0_real64,0.0_real64]
    xy(:,2)=[1.0_real64,1.0_real64]
    xy(:,3)=[2.0_real64,2.0_real64]
    phi=[1.0_real64,2.0_real64,3.0_real64]
    call triangle_pressure_force(xy,phi,0.30_real64,0.25_real64, &
                                gradient,acceleration,ok)
    call check(.not.ok,'collinear triangle is rejected',failures)
    call check_nan_vector([gradient,acceleration], &
                          'degenerate geometry returns all NaN',failures)

    phi(2)=nan
    bad_xy=reshape([0.0_real64,0.0_real64,1.0_real64,0.0_real64, &
                    0.0_real64,1.0_real64],[2,3])
    call triangle_pressure_force(bad_xy,phi, &
                                0.30_real64,0.25_real64,gradient,acceleration,ok)
    call check(.not.ok,'nonfinite scalar is rejected',failures)
    call check_nan_vector([gradient,acceleration], &
                          'nonfinite scalar returns all NaN',failures)
  end subroutine test_nan_and_degenerate_failures

end program test_qbal_relative_pressure_force
