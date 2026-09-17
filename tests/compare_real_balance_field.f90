program compare_real_balance_field
  use, intrinsic :: iso_fortran_env, only: real64, int64
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use netcdf
  implicit none

  character(1024) :: before_path, after_path, variable
  character(256) :: before_units, after_units
  integer :: before_nc, after_nc, before_var, after_var, before_type, after_type
  integer :: i, j, k, l
  integer :: before_dims(4), after_dims(4)
  real(real64), allocatable :: before(:,:,:,:), after(:,:,:,:)
  real(real64) :: before_fill, after_fill, before_missing, after_missing
  logical :: before_has_fill, after_has_fill, before_has_missing, after_has_missing
  logical :: before_valid, after_valid
  integer(int64) :: common_valid, before_only, after_only, invalid_both, changed
  real(real64) :: sum_before, sum_after, sum_square, max_abs, difference

  if (command_argument_count() /= 3) call fail( &
    'usage: compare_real_balance_field BEFORE AFTER VARIABLE')
  call get_command_argument(1, before_path)
  call get_command_argument(2, after_path)
  call get_command_argument(3, variable)

  call inspect(trim(before_path), trim(variable), before_nc, before_var, before_type, &
               before_dims, before_units, before_fill, before_has_fill, before_missing, before_has_missing)
  call inspect(trim(after_path), trim(variable), after_nc, after_var, after_type, &
               after_dims, after_units, after_fill, after_has_fill, after_missing, after_has_missing)
  if (before_type /= after_type .or. any(before_dims /= after_dims)) &
    call fail('field schema differs between files')
  if (trim(before_units) /= trim(after_units)) call fail('field units differ between files')
  call compare_coordinate(before_nc, after_nc, 'level', 'z')
  call compare_coordinate(before_nc, after_nc, 'valtime', 'record')
  call compare_coordinate(before_nc, after_nc, 'reftime', 'record')

  allocate(before(before_dims(1),before_dims(2),before_dims(3),before_dims(4)))
  allocate(after(after_dims(1),after_dims(2),after_dims(3),after_dims(4)))
  call nc_check(nf90_get_var(before_nc, before_var, before), 'read before field')
  call nc_check(nf90_get_var(after_nc, after_var, after), 'read after field')
  call nc_check(nf90_close(before_nc), 'close before file')
  call nc_check(nf90_close(after_nc), 'close after file')

  common_valid = 0_int64
  before_only = 0_int64
  after_only = 0_int64
  invalid_both = 0_int64
  changed = 0_int64
  sum_before = 0.0_real64
  sum_after = 0.0_real64
  sum_square = 0.0_real64
  max_abs = 0.0_real64
  do l = 1, before_dims(4)
    do k = 1, before_dims(3)
      do j = 1, before_dims(2)
        do i = 1, before_dims(1)
          before_valid = usable(before(i,j,k,l), before_has_fill, before_fill, &
                                before_has_missing, before_missing)
          after_valid = usable(after(i,j,k,l), after_has_fill, after_fill, &
                               after_has_missing, after_missing)
          if (before_valid .and. after_valid) then
            common_valid = common_valid + 1_int64
            difference = after(i,j,k,l) - before(i,j,k,l)
            sum_before = sum_before + before(i,j,k,l)
            sum_after = sum_after + after(i,j,k,l)
            sum_square = sum_square + difference*difference
            max_abs = max(max_abs, abs(difference))
            if (before(i,j,k,l) /= after(i,j,k,l)) changed = changed + 1_int64
          else if (before_valid) then
            before_only = before_only + 1_int64
          else if (after_valid) then
            after_only = after_only + 1_int64
          else
            invalid_both = invalid_both + 1_int64
          end if
        end do
      end do
    end do
  end do
  if (common_valid == 0_int64) call fail('no common-valid cells to compare')

  print '(a)', 'COMPARISON_COMPLETE'
  print '(a,a)', 'variable = ', trim(variable)
  print '(a,a)', 'units = ', trim(before_units)
  print '(a,i0)', 'common_valid = ', common_valid
  print '(a,i0)', 'before_only_valid = ', before_only
  print '(a,i0)', 'after_only_valid = ', after_only
  print '(a,i0)', 'invalid_both = ', invalid_both
  print '(a,i0)', 'changed_cells = ', changed
  print '(a,es24.16)', 'rms_diff = ', sqrt(sum_square/real(common_valid,real64))
  print '(a,es24.16)', 'max_abs_diff = ', max_abs
  print '(a,es24.16)', 'mean_before = ', sum_before/real(common_valid,real64)
  print '(a,es24.16)', 'mean_after = ', sum_after/real(common_valid,real64)
  print '(a)', 'statistics_over = common_valid_cells'

contains

  subroutine fail(message)
    character(*), intent(in) :: message
    print '(a)', 'FAIL: '//trim(message)
    error stop 1
  end subroutine fail

  subroutine nc_check(code, where)
    integer, intent(in) :: code
    character(*), intent(in) :: where
    if (code /= nf90_noerr) call fail(trim(where)//': '//trim(nf90_strerror(code)))
  end subroutine nc_check

  subroutine inspect(path, name, ncid, varid, xtype, dims, units, &
                     fill, has_fill, missing, has_missing)
    character(*), intent(in) :: path, name
    integer, intent(out) :: ncid, varid, xtype, dims(4)
    character(*), intent(out) :: units
    real(real64), intent(out) :: fill, missing
    logical, intent(out) :: has_fill, has_missing
    integer :: d, rank, dimids(nf90_max_var_dims)
    character(64) :: dim_name
    ! NetCDF Fortran exposes the on-disk record,z,y,x field as x,y,z,record.
    character(8), parameter :: expected_name(4) = [character(8) :: 'x','y','z','record']
    integer, parameter :: expected_len(4) = [235,283,22,1]

    call nc_check(nf90_open(path, nf90_nowrite, ncid), 'open '//trim(path))
    call nc_check(nf90_inq_varid(ncid, name, varid), 'find variable '//trim(name))
    call nc_check(nf90_inquire_variable(ncid, varid, xtype=xtype, ndims=rank, &
                                        dimids=dimids), 'inspect variable '//trim(name))
    if (rank /= 4 .or. (xtype /= nf90_float .and. xtype /= nf90_double)) &
      call fail('variable must be a rank-4 real field')
    do d = 1, 4
      dim_name = ''
      call nc_check(nf90_inquire_dimension(ncid, dimids(d), name=dim_name, len=dims(d)), &
                    'inspect field dimension')
      if (trim(dim_name) /= expected_name(d) .or. dims(d) /= expected_len(d)) &
        call fail('expected LAPS x,y,z,record dimensions')
    end do
    units = ''
    call nc_check(nf90_get_att(ncid, varid, 'units', units), 'read field units')
    if (len_trim(units) == 0) call fail('field units attribute is empty')
    call read_marker(ncid, varid, '_FillValue', fill, has_fill)
    call read_marker(ncid, varid, 'missing_value', missing, has_missing)
  end subroutine inspect

  subroutine compare_coordinate(before_nc, after_nc, name, wanted_dim)
    integer, intent(in) :: before_nc, after_nc
    character(*), intent(in) :: name, wanted_dim
    integer :: before_id, after_id, before_type, after_type, before_rank, after_rank
    integer :: before_dim(nf90_max_var_dims), after_dim(nf90_max_var_dims)
    integer :: before_len, after_len, idx
    character(64) :: before_dim_name, after_dim_name
    character(256) :: before_units, after_units
    real(real64), allocatable :: before_value(:), after_value(:)
    real(real64) :: before_fill, after_fill, before_missing, after_missing
    logical :: before_has_fill, after_has_fill, before_has_missing, after_has_missing
    logical :: before_valid, after_valid
    call nc_check(nf90_inq_varid(before_nc, name, before_id), 'find '//trim(name))
    call nc_check(nf90_inq_varid(after_nc, name, after_id), 'find '//trim(name))
    call nc_check(nf90_inquire_variable(before_nc, before_id, xtype=before_type, &
                                        ndims=before_rank, dimids=before_dim), 'inspect coordinate')
    call nc_check(nf90_inquire_variable(after_nc, after_id, xtype=after_type, &
                                        ndims=after_rank, dimids=after_dim), 'inspect coordinate')
    if (before_type /= after_type .or. before_rank /= 1 .or. after_rank /= 1 .or. &
        (before_type /= nf90_float .and. before_type /= nf90_double)) &
      call fail('coordinate schema differs: '//trim(name))
    before_dim_name = ''; after_dim_name = ''
    call nc_check(nf90_inquire_dimension(before_nc, before_dim(1), name=before_dim_name, len=before_len), &
                  'inspect coordinate dimension')
    call nc_check(nf90_inquire_dimension(after_nc, after_dim(1), name=after_dim_name, len=after_len), &
                  'inspect coordinate dimension')
    if (trim(before_dim_name) /= wanted_dim .or. trim(after_dim_name) /= wanted_dim .or. &
        before_len /= after_len) call fail('coordinate dimension differs: '//trim(name))
    before_units = ''; after_units = ''
    call nc_check(nf90_get_att(before_nc, before_id, 'units', before_units), 'read coordinate units')
    call nc_check(nf90_get_att(after_nc, after_id, 'units', after_units), 'read coordinate units')
    if (len_trim(before_units) == 0 .or. len_trim(after_units) == 0) &
      call fail('coordinate units are empty: '//trim(name))
    if (trim(before_units) /= trim(after_units)) call fail('coordinate units differ: '//trim(name))
    call read_marker(before_nc, before_id, '_FillValue', before_fill, before_has_fill)
    call read_marker(after_nc, after_id, '_FillValue', after_fill, after_has_fill)
    call read_marker(before_nc, before_id, 'missing_value', before_missing, before_has_missing)
    call read_marker(after_nc, after_id, 'missing_value', after_missing, after_has_missing)
    allocate(before_value(before_len), after_value(after_len))
    call nc_check(nf90_get_var(before_nc, before_id, before_value), 'read '//trim(name))
    call nc_check(nf90_get_var(after_nc, after_id, after_value), 'read '//trim(name))
    do idx = 1, SIZE(before_value)
      before_valid = usable(before_value(idx), before_has_fill, before_fill, &
                            before_has_missing, before_missing)
      after_valid = usable(after_value(idx), after_has_fill, after_fill, &
                           after_has_missing, after_missing)
      if (.not.before_valid .or. .not.after_valid) &
        call fail('invalid coordinate: '//trim(name))
      if (before_value(idx) /= after_value(idx)) &
        call fail('coordinate values differ: '//trim(name))
    end do
    deallocate(before_value, after_value)
  end subroutine compare_coordinate

  subroutine read_marker(ncid, varid, name, value, present)
    integer, intent(in) :: ncid, varid
    character(*), intent(in) :: name
    real(real64), intent(out) :: value
    logical, intent(out) :: present
    integer :: code, xtype, length

    value = 0.0_real64
    present = .false.
    code = nf90_inquire_attribute(ncid, varid, name, xtype=xtype, len=length)
    if (code == nf90_enotatt) return
    call nc_check(code, 'inspect '//trim(name))
    if ((xtype /= nf90_float .and. xtype /= nf90_double) .or. length /= 1) &
      call fail('marker must be one real scalar: '//trim(name))
    call nc_check(nf90_get_att(ncid, varid, name, value), 'read '//trim(name))
    if (ieee_is_finite(value)) present = .true.
  end subroutine read_marker

  logical function usable(value, has_fill, fill, has_missing, missing)
    real(real64), intent(in) :: value, fill, missing
    logical, intent(in) :: has_fill, has_missing
    usable = .false.
    if (.not.ieee_is_finite(value)) return
    usable = .true.
    if (has_fill) then
      if (value == fill) usable = .false.
    end if
    if (has_missing) then
      if (value == missing) usable = .false.
    end if
  end function usable

end program compare_real_balance_field
