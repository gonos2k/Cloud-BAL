program test_qbal_real_operator
  use, intrinsic :: iso_fortran_env, only: int32, int64, real32, real64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  implicit none

  integer :: nx, ny, nz, i, j, k, unit, output_unit, io_status
  integer :: point_status, setup_status, metric_status
  integer(int64) :: raw_nonzero, discarded_nonzero, active_count
  integer(int64) :: active_boundary_count
  integer(int32) :: header(4), cell(3)
  integer(int64) :: before_counts(2,2), hypothetical_counts(2,2)
  real(real32) :: erf, residual
  real(real32), allocatable :: s(:,:,:), f(:,:,:), erru(:,:,:), beta(:,:,:)
  real(real32), allocatable :: tau(:,:), dx(:,:), dy(:,:), ps(:,:), p(:), dp(:)
  real(real32), allocatable :: u(:,:,:), v(:,:,:), w(:,:,:)
  real(real32), allocatable :: du(:,:,:), dv(:,:,:), dw(:,:,:)
  real(real32), allocatable :: u_hyp(:,:,:), v_hyp(:,:,:), w_hyp(:,:,:)
  real(real64), allocatable :: lambda(:,:,:), cx(:,:,:), cy(:,:,:), cp(:,:,:)
  real(real64), allocatable :: rhs(:,:,:)
  logical, allocatable :: active(:,:,:)
  real(real64) :: c(6), a_lambda, dg_lambda, defect
  real(real64) :: roundoff_bound, term_scale
  real(real64) :: rhs_sum, rhs_max, legacy_sum, legacy_max
  real(real64) :: ag_sum, ag_max, ag_value_sum, ag_value_max
  real(real64) :: rhs_bound_max, ag_bound_max
  real(real64) :: identity_sum(2), identity_max(2), identity_bound_max(2)
  integer(int64) :: rhs_count, legacy_count, ag_count
  integer(int64) :: rhs_bound_failures, ag_bound_failures
  integer(int64) :: identity_count(2), identity_bound_failures(2)
  real(real32) :: before_residual, delta_residual, after_residual
  integer :: nrows
  character(len=1024) :: snapshot_path, output_path
  real(real64), parameter :: roundoff_factor = 256.0_real64
  real(real64), parameter :: float32_epsilon = &
       real(epsilon(1.0_real32), real64)

  external :: continuity_point, qbal_continuity_setup
  external :: qbal_continuity_row, qbal_multiplier_increment
  real(real64), external :: qbal_row_value

  call get_command_argument(1, snapshot_path)
  call get_command_argument(2, output_path)
  if (len_trim(snapshot_path) == 0 .or. len_trim(output_path) == 0) then
    print *, 'usage: test_qbal_real_operator SNAPSHOT OUTPUT_ROWS'
    error stop 2
  end if

  open(newunit=unit, file=trim(snapshot_path), access='stream', &
       form='unformatted', status='old', convert='big_endian', &
       iostat=io_status)
  if (io_status /= 0) error stop 'cannot open actual operator snapshot'
  read(unit, iostat=io_status) nx, ny, nz, erf
  if (io_status /= 0) error stop 'cannot read actual operator header'
  if (nx /= 235 .or. ny /= 283 .or. nz /= 22) then
    print *, 'unexpected snapshot dimensions ', nx, ny, nz
    error stop 2
  end if
  if (.not. ieee_is_finite(erf) .or. erf <= 0.0_real32) then
    error stop 'invalid stored relaxation tolerance'
  end if

  allocate(s(nx+1,ny+1,nz+1), f(nx+1,ny+1,nz+1), &
           erru(nx,ny,nz), beta(nx,ny,nz))
  allocate(tau(nx,ny), dx(nx,ny), dy(nx,ny), ps(nx,ny), p(nz), dp(nz))
  allocate(u(nx,ny,nz), v(nx,ny,nz), w(nx,ny,nz))
  read(unit, iostat=io_status) s, f, erru, beta, tau, dx, dy, ps, p, dp
  if (io_status /= 0) error stop 'cannot read actual operator coefficient arrays'
  read(unit, iostat=io_status) u, v, w
  close(unit)
  if (io_status /= 0) error stop 'cannot read actual operator wind arrays'
  if (any(.not. ieee_is_finite(s)) .or. any(.not. ieee_is_finite(f))) then
    error stop 'nonfinite stored multiplier or legacy RHS'
  end if

  allocate(lambda(nx+1,ny+1,nz+1), rhs(nx+1,ny+1,nz+1), &
           active(nx+1,ny+1,nz+1))
  allocate(cx(nx,ny,nz), cy(nx,ny,nz), cp(nx,ny,nz))
  allocate(du(nx,ny,nz), dv(nx,ny,nz), dw(nx,ny,nz))
  allocate(u_hyp(nx,ny,nz), v_hyp(nx,ny,nz), w_hyp(nx,ny,nz))

  call qbal_continuity_setup(u, v, w, erru, tau, beta, nx, ny, nz, &
       dx, dy, ps, p, dp, active, cx, cy, cp, rhs, setup_status)
  if (setup_status /= 1) error stop 'production continuity setup failed'
  active_count = int(count(active), int64)
  if (active_count <= 0_int64) error stop 'actual snapshot has no active rows'
  active_boundary_count = 0_int64
  do k = 2, nz
    do j = 2, ny
      do i = 2, nx
        if (active(i,j,k) .and. &
            (i == 2 .or. i == nx .or. j == 2 .or. j == ny .or. &
             k == 2 .or. k == nz)) active_boundary_count = &
             active_boundary_count + 1_int64
      end do
    end do
  end do

  lambda = 0.0_real64
  raw_nonzero = 0_int64
  discarded_nonzero = 0_int64
  do k = 1, nz+1
    do j = 1, ny+1
      do i = 1, nx+1
        if (s(i,j,k) /= 0.0_real32) raw_nonzero = raw_nonzero + 1_int64
        if (active(i,j,k)) then
          lambda(i,j,k) = real(s(i,j,k), real64)
        else if (s(i,j,k) /= 0.0_real32) then
          discarded_nonzero = discarded_nonzero + 1_int64
        end if
      end do
    end do
  end do
  print *, 'ACTUAL_OPERATOR dimensions ', nx, ny, nz, ' erf ', erf
  print *, 'ACTUAL_OPERATOR active rows ', active_count
  print *, 'ACTUAL_OPERATOR active boundary-mask rows ', active_boundary_count
  print *, 'ACTUAL_OPERATOR raw nonzero lambda / discarded inactive-ghost ', &
       raw_nonzero, discarded_nonzero
  print *, 'ACTUAL_OPERATOR lambda restriction: stored real4 lambda cast to real8; '// &
       'inactive and ghost entries set to zero'

  call report_state('before', u, v, w, active, nx, ny, nz, dx, dy, ps, p, dp, &
       before_counts, metric_status)
  if (metric_status /= 1) error stop 'cannot measure actual before residual'

  call qbal_multiplier_increment(lambda, cx, cy, cp, nx, ny, nz, du, dv, dw)
  u_hyp = u + du
  v_hyp = v + dv
  w_hyp = w + dw
  call report_state('hypothetical_delta', u_hyp, v_hyp, w_hyp, active, nx, ny, nz, &
       dx, dy, ps, p, dp, hypothetical_counts, metric_status)
  if (metric_status /= 1) error stop 'cannot measure hypothetical delta residual'
  if (any(before_counts /= hypothetical_counts)) then
    error stop 'before and hypothetical residual domains differ'
  end if

  identity_sum = 0.0_real64
  identity_max = 0.0_real64
  identity_bound_max = 0.0_real64
  identity_count = 0_int64
  identity_bound_failures = 0_int64
  do k = 2, nz
    do j = 2, ny
      do i = 2, nx
        if (ps(i,j) < p(k)) cycle
        call continuity_point(u, v, w, nx, ny, nz, dx, dy, dp, &
             i, j, k, before_residual, point_status)
        if (point_status == 0) error stop 'before identity row lost status'
        if (point_status /= 1) cycle
        call continuity_point(u_hyp, v_hyp, w_hyp, nx, ny, nz, dx, dy, dp, &
             i, j, k, after_residual, point_status)
        if (point_status /= 1) error stop 'hypothetical identity row lost status'
        call continuity_point(du, dv, dw, nx, ny, nz, dx, dy, dp, &
             i, j, k, delta_residual, point_status)
        if (point_status /= 1) error stop 'delta identity row lost status'
        defect = real(after_residual,real64) - real(before_residual,real64) &
             - real(delta_residual,real64)
        term_scale = abs(real(u_hyp(i,j-1,k-1),real64)/real(dx(i,j),real64)) &
             + abs(real(u_hyp(i-1,j-1,k-1),real64)/real(dx(i,j),real64)) &
             + abs(real(v_hyp(i-1,j,k-1),real64)/real(dy(i,j),real64)) &
             + abs(real(v_hyp(i-1,j-1,k-1),real64)/real(dy(i,j),real64)) &
             + abs(real(w_hyp(i,j,k-1),real64)/real(dp(k),real64)) &
             + abs(real(w_hyp(i,j,k),real64)/real(dp(k),real64)) &
             + abs(real(u(i,j-1,k-1),real64)/real(dx(i,j),real64)) &
             + abs(real(u(i-1,j-1,k-1),real64)/real(dx(i,j),real64)) &
             + abs(real(v(i-1,j,k-1),real64)/real(dy(i,j),real64)) &
             + abs(real(v(i-1,j-1,k-1),real64)/real(dy(i,j),real64)) &
             + abs(real(w(i,j,k-1),real64)/real(dp(k),real64)) &
             + abs(real(w(i,j,k),real64)/real(dp(k),real64))
        roundoff_bound = roundoff_factor*float32_epsilon*max(1.0e-30_real64, &
             term_scale)
        call accumulate_identity(1_int64, defect, roundoff_bound)
        if (active(i,j,k)) call accumulate_identity(2_int64, defect, roundoff_bound)
      end do
    end do
  end do
  if (identity_count(1) <= 0_int64 .or. identity_count(2) <= 0_int64) then
    error stop 'identity diagnostics have no rows'
  end if
  print *, 'ACTUAL_OPERATOR D(y+G_lambda)-D(y)-D(G_lambda) full count RMS max ', &
       identity_count(1), sqrt(identity_sum(1)/real(identity_count(1),real64)), &
       identity_max(1)
  print *, 'ACTUAL_OPERATOR identity full roundoff bound max / failures ', &
       identity_bound_max(1), identity_bound_failures(1)
  print *, 'ACTUAL_OPERATOR D(y+G_lambda)-D(y)-D(G_lambda) support count RMS max ', &
       identity_count(2), sqrt(identity_sum(2)/real(identity_count(2),real64)), &
       identity_max(2)
  print *, 'ACTUAL_OPERATOR identity support roundoff bound max / failures ', &
       identity_bound_max(2), identity_bound_failures(2)
  if (any(identity_bound_failures /= 0_int64)) then
    error stop 'continuity increment identity exceeded declared float32 roundoff bound'
  end if

  rhs_sum = 0.0_real64
  rhs_max = 0.0_real64
  legacy_sum = 0.0_real64
  legacy_max = 0.0_real64
  ag_sum = 0.0_real64
  ag_max = 0.0_real64
  ag_value_sum = 0.0_real64
  ag_value_max = 0.0_real64
  rhs_bound_max = 0.0_real64
  ag_bound_max = 0.0_real64
  rhs_count = 0_int64
  legacy_count = 0_int64
  ag_count = 0_int64
  rhs_bound_failures = 0_int64
  ag_bound_failures = 0_int64
  do k = 2, nz
    do j = 2, ny
      do i = 2, nx
        if (.not. active(i,j,k)) cycle
        call continuity_point(u, v, w, nx, ny, nz, dx, dy, dp, &
             i, j, k, residual, point_status)
        if (point_status /= 1) error stop 'active actual row lost continuity status'
        defect = rhs(i,j,k) + real(residual, real64)
        roundoff_bound = roundoff_factor*float32_epsilon*max(1.0e-30_real64, &
             abs(rhs(i,j,k)) + abs(real(residual, real64)))
        rhs_sum = rhs_sum + defect*defect
        rhs_max = max(rhs_max, abs(defect))
        rhs_bound_max = max(rhs_bound_max, roundoff_bound)
        if (abs(defect) > roundoff_bound) rhs_bound_failures = &
             rhs_bound_failures + 1_int64
        rhs_count = rhs_count + 1_int64
        defect = rhs(i,j,k) - real(f(i,j,k), real64)
        legacy_sum = legacy_sum + defect*defect
        legacy_max = max(legacy_max, abs(defect))
        legacy_count = legacy_count + 1_int64

        call qbal_continuity_row(cx, cy, cp, nx, ny, nz, dx, dy, dp, &
             i, j, k, c)
        a_lambda = qbal_row_value(lambda, nx, ny, nz, i, j, k, c)
        call continuity_point(du, dv, dw, nx, ny, nz, dx, dy, dp, &
             i, j, k, residual, point_status)
        if (point_status /= 1) error stop 'active DG row lost continuity status'
        dg_lambda = real(residual, real64)
        defect = a_lambda - dg_lambda
        term_scale = abs(real(du(i,j-1,k-1),real64)/real(dx(i,j),real64)) &
             + abs(real(du(i-1,j-1,k-1),real64)/real(dx(i,j),real64)) &
             + abs(real(dv(i-1,j,k-1),real64)/real(dy(i,j),real64)) &
             + abs(real(dv(i-1,j-1,k-1),real64)/real(dy(i,j),real64)) &
             + abs(real(dw(i,j,k-1),real64)/real(dp(k),real64)) &
             + abs(real(dw(i,j,k),real64)/real(dp(k),real64))
        roundoff_bound = roundoff_factor*float32_epsilon*max(1.0e-30_real64, &
             abs(a_lambda) + abs(dg_lambda) + term_scale)
        ag_sum = ag_sum + defect*defect
        ag_max = max(ag_max, abs(defect))
        ag_bound_max = max(ag_bound_max, roundoff_bound)
        if (abs(defect) > roundoff_bound) ag_bound_failures = &
             ag_bound_failures + 1_int64
        ag_count = ag_count + 1_int64
        ag_value_sum = ag_value_sum + a_lambda*a_lambda
        ag_value_max = max(ag_value_max, abs(a_lambda))
      end do
    end do
  end do
  if (rhs_count <= 0_int64 .or. ag_count <= 0_int64) then
    error stop 'active diagnostics have no rows'
  end if
  if (ag_value_max <= 0.0_real64) error stop 'zero A_lambda oracle'
  print *, 'ACTUAL_OPERATOR rhs vs -D(actual) count RMS max ', rhs_count, &
       sqrt(rhs_sum/real(rhs_count,real64)), rhs_max
  print *, 'ACTUAL_OPERATOR rhs roundoff bound max / failures ', &
       rhs_bound_max, rhs_bound_failures
  print *, 'ACTUAL_OPERATOR new rhs vs stored legacy f count RMS max ', &
       legacy_count, sqrt(legacy_sum/real(legacy_count,real64)), legacy_max
  print *, 'ACTUAL_OPERATOR A_lambda vs DG_lambda count RMS max ', ag_count, &
       sqrt(ag_sum/real(ag_count,real64)), ag_max
  print *, 'ACTUAL_OPERATOR A_lambda roundoff bound max / failures ', &
       ag_bound_max, ag_bound_failures
  print *, 'ACTUAL_OPERATOR A_lambda RMS max ', &
       sqrt(ag_value_sum/real(ag_count,real64)), ag_value_max
  if (rhs_bound_failures /= 0_int64 .or. ag_bound_failures /= 0_int64) then
    error stop 'shared operator comparison exceeded declared float32 roundoff bound'
  end if

  header = [int(nx,int32), int(ny,int32), int(nz,int32), int(active_count,int32)]
  open(newunit=output_unit, file=trim(output_path), access='stream', &
       form='unformatted', status='replace', convert='little_endian', &
       iostat=io_status)
  if (io_status /= 0) error stop 'cannot open sparse row export'
  write(output_unit, iostat=io_status) header
  if (io_status /= 0) error stop 'cannot write sparse row header'
  nrows = 0
  do k = 2, nz
    do j = 2, ny
      do i = 2, nx
        if (.not. active(i,j,k)) cycle
        call qbal_continuity_row(cx, cy, cp, nx, ny, nz, dx, dy, dp, &
             i, j, k, c)
        cell = [int(i,int32), int(j,int32), int(k,int32)]
        write(output_unit, iostat=io_status) cell, rhs(i,j,k), c
        if (io_status /= 0) error stop 'cannot write sparse row export'
        nrows = nrows + 1
      end do
    end do
  end do
  close(output_unit)
  if (nrows /= int(active_count)) error stop 'sparse row count changed during export'
  print *, 'ACTUAL_OPERATOR sparse rows ', trim(output_path), ' count ', nrows
  print *, 'ACTUAL_OPERATOR sparse format: little-endian int32 nx ny nz nrows; '// &
       'int32 i j k; float64 rhs,c(E,W,N,S,upper,lower)'
  print *, 'ACTUAL_OPERATOR audit complete: diagnostic only; no after-state acceptance'

contains

  subroutine accumulate_identity(category, value, bound)
    integer(int64), intent(in) :: category
    real(real64), intent(in) :: value, bound
    integer :: index
    index = int(category)
    identity_count(index) = identity_count(index) + 1_int64
    identity_sum(index) = identity_sum(index) + value*value
    identity_max(index) = max(identity_max(index), abs(value))
    identity_bound_max(index) = max(identity_bound_max(index), bound)
    if (abs(value) > bound) identity_bound_failures(index) = &
         identity_bound_failures(index) + 1_int64
  end subroutine accumulate_identity

  subroutine report_state(label, ua, va, wa, row_active, nxi, nyi, nzi, &
       dxi, dyi, psi, pi, dpi, counts, status_out)
    character(len=*), intent(in) :: label
    integer, intent(in) :: nxi, nyi, nzi
    real(real32), intent(in) :: ua(nxi,nyi,nzi), va(nxi,nyi,nzi), wa(nxi,nyi,nzi)
    real(real32), intent(in) :: dxi(nxi,nyi), dyi(nxi,nyi), psi(nxi,nyi)
    real(real32), intent(in) :: pi(nzi), dpi(nzi)
    logical, intent(in) :: row_active(nxi+1,nyi+1,nzi+1)
    integer(int64), intent(out) :: counts(2,2)
    integer, intent(out) :: status_out
    integer :: ii, jj, kk, status_local
    integer(int64) :: count_local(2)
    real(real64) :: sum_local(2), max_local(2), value_local
    real(real32) :: point_residual

    status_out = 0
    counts = 0_int64
    count_local = 0_int64
    sum_local = 0.0_real64
    max_local = 0.0_real64
    do kk = 2, nzi
      do jj = 2, nyi
        do ii = 2, nxi
          if (psi(ii,jj) < pi(kk)) cycle
          call continuity_point(ua, va, wa, nxi, nyi, nzi, dxi, dyi, dpi, &
               ii, jj, kk, point_residual, status_local)
          if (status_local == 0) return
          if (status_local /= 1) cycle
          value_local = real(point_residual, real64)
          count_local(1) = count_local(1) + 1_int64
          sum_local(1) = sum_local(1) + value_local*value_local
          max_local(1) = max(max_local(1), abs(value_local))
          if (row_active(ii,jj,kk)) then
            count_local(2) = count_local(2) + 1_int64
            sum_local(2) = sum_local(2) + value_local*value_local
            max_local(2) = max(max_local(2), abs(value_local))
          end if
        end do
      end do
    end do
    if (count_local(1) <= 0_int64 .or. count_local(2) <= 0_int64) return
    print *, 'ACTUAL_OPERATOR unweighted ', trim(label), ' full count/RMS/max ', &
         count_local(1), sqrt(sum_local(1)/real(count_local(1),real64)), max_local(1)
    print *, 'ACTUAL_OPERATOR unweighted ', trim(label), ' support count/RMS/max ', &
         count_local(2), sqrt(sum_local(2)/real(count_local(2),real64)), max_local(2)
    counts(1,1) = count_local(1)
    counts(1,2) = count_local(2)
    status_out = 1
  end subroutine report_state

end program test_qbal_real_operator
