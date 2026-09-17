program verify_real_full_domain
  use iso_fortran_env, only: int8,int64
  use netcdf
  implicit none
  character(1024) :: ref_met,new_met,ref_wrf,new_wrf

  if (command_argument_count()/=4) call fail( &
    'usage: verify_real_full_domain reference_met new_met reference_wrf new_wrf')
  call get_command_argument(1,ref_met); call get_command_argument(2,new_met)
  call get_command_argument(3,ref_wrf); call get_command_argument(4,new_wrf)
  call inspect(trim(ref_met),'met_em'); call inspect(trim(new_met),'met_em')
  call inspect(trim(ref_wrf),'wrfinput'); call inspect(trim(new_wrf),'wrfinput')
  call compare_bytes(trim(ref_met),trim(new_met),'met_em')
  call compare_bytes(trim(ref_wrf),trim(new_wrf),'wrfinput')
  print '(a)', 'PASS_SCOPED: real full-domain replay byte-identical for met_em and wrfinput'
  print '(a)', 'SCOPE_ONLY: no native-consumed or physics validation performed'

contains
  subroutine fail(message)
    character(*), intent(in) :: message
    print '(a)', 'FAIL: '//trim(message); error stop 1
  end subroutine fail

  subroutine nc(status,where)
    integer, intent(in) :: status; character(*), intent(in) :: where
    if (status/=nf90_noerr) call fail(trim(where)//': '//trim(nf90_strerror(status)))
  end subroutine nc

  subroutine inspect(path,kind)
    character(*), intent(in) :: path,kind
    integer :: file
    call nc(nf90_open(path,nf90_nowrite,file),'open '//trim(path))
    call dimension_is(file,'Time',1); call dimension_is(file,'DateStrLen',19)
    call dimension_is(file,'west_east',234); call dimension_is(file,'south_north',282)
    call dimension_is(file,'west_east_stag',235); call dimension_is(file,'south_north_stag',283)
    call variable_is(file,'Times',nf90_char,[character(32)::'DateStrLen','Time'])
    call time_is(file)
    if (kind=='met_em') then
      call dimension_is(file,'num_metgrid_levels',21)
      call variable_is(file,'PRES',nf90_float,[character(32)::'west_east','south_north', &
        'num_metgrid_levels','Time'])
      call variable_is(file,'TT',nf90_float,[character(32)::'west_east','south_north', &
        'num_metgrid_levels','Time'])
      call variable_is(file,'QV',nf90_float,[character(32)::'west_east','south_north', &
        'num_metgrid_levels','Time'])
      call variable_is(file,'GHT',nf90_float,[character(32)::'west_east','south_north', &
        'num_metgrid_levels','Time'])
      call variable_is(file,'UU',nf90_float,[character(32)::'west_east_stag','south_north', &
        'num_metgrid_levels','Time'])
      call variable_is(file,'VV',nf90_float,[character(32)::'west_east','south_north_stag', &
        'num_metgrid_levels','Time'])
      call variable_is(file,'PSFC',nf90_float,[character(32)::'west_east','south_north','Time'])
    else
      call dimension_is(file,'bottom_top',39); call dimension_is(file,'bottom_top_stag',40)
      call variable_is(file,'W',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top_stag','Time'])
      call variable_is(file,'U',nf90_float,[character(32)::'west_east_stag','south_north', &
        'bottom_top','Time'])
      call variable_is(file,'V',nf90_float,[character(32)::'west_east','south_north_stag', &
        'bottom_top','Time'])
      call variable_is(file,'T',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top','Time'])
      call variable_is(file,'P',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top','Time'])
      call variable_is(file,'PB',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top','Time'])
      call variable_is(file,'QVAPOR',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top','Time'])
      call variable_is(file,'PH',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top_stag','Time'])
      call variable_is(file,'PHB',nf90_float,[character(32)::'west_east','south_north', &
        'bottom_top_stag','Time'])
      call variable_is(file,'XLAT',nf90_float,[character(32)::'west_east','south_north','Time'])
      call variable_is(file,'XLONG',nf90_float,[character(32)::'west_east','south_north','Time'])
    end if
    call nc(nf90_close(file),'close '//trim(path))
  end subroutine inspect

  subroutine dimension_is(file,name,want)
    integer, intent(in) :: file,want
    character(*), intent(in) :: name
    integer :: id,length
    call nc(nf90_inq_dimid(file,name,id),'find dimension '//trim(name))
    call nc(nf90_inquire_dimension(file,id,len=length),'read dimension '//trim(name))
    if (length/=want) call fail('dimension '//trim(name)//' has unexpected length')
  end subroutine dimension_is

  subroutine variable_is(file,name,want_type,want_dims)
    integer, intent(in) :: file,want_type
    character(*), intent(in) :: name,want_dims(:)
    integer :: id,actual_type,rank,dimids(nf90_max_var_dims),d
    character(256) :: actual_dim
    call nc(nf90_inq_varid(file,name,id),'find variable '//trim(name))
    call nc(nf90_inquire_variable(file,id,xtype=actual_type,ndims=rank,dimids=dimids), &
      'read variable '//trim(name))
    if (actual_type/=want_type .or. rank/=size(want_dims)) &
      call fail('schema mismatch for variable '//trim(name))
    do d=1,rank
      actual_dim=''
      call nc(nf90_inquire_dimension(file,dimids(d),name=actual_dim), &
        'read variable dimension '//trim(name))
      if (trim(actual_dim)/=trim(want_dims(d))) call fail('dimension order mismatch for '//trim(name))
    end do
  end subroutine variable_is

  subroutine time_is(file)
    integer, intent(in) :: file
    integer :: id
    character(19) :: times(1)
    call nc(nf90_inq_varid(file,'Times',id),'find Times')
    call nc(nf90_get_var(file,id,times),'read Times')
    if (times(1)/='2026-08-16_13:00:00') call fail('unexpected Times value')
  end subroutine time_is

  subroutine compare_bytes(reference,replay,label)
    character(*), intent(in) :: reference,replay,label
    integer(int64) :: reference_size,replay_size,offset,total,n64
    integer :: ru,nu,n,ios,i
    integer(int8) :: a(1048576),b(1048576)
    inquire(file=reference,size=reference_size,iostat=ios)
    if (ios/=0) call fail('cannot stat '//trim(reference))
    inquire(file=replay,size=replay_size,iostat=ios)
    if (ios/=0) call fail('cannot stat '//trim(replay))
    if (reference_size/=replay_size) call fail(trim(label)//' file size mismatch')
    open(newunit=ru,file=reference,status='old',action='read',access='stream',form='unformatted',iostat=ios)
    if (ios/=0) call fail('cannot open '//trim(reference))
    open(newunit=nu,file=replay,status='old',action='read',access='stream',form='unformatted',iostat=ios)
    if (ios/=0) call fail('cannot open '//trim(replay))
    offset=0_int64; total=reference_size
    do while (offset<total)
      n64=min(int(size(a),int64),total-offset); n=int(n64)
      read(ru,iostat=ios) a(1:n); if (ios/=0) call fail('read reference failed')
      read(nu,iostat=ios) b(1:n); if (ios/=0) call fail('read replay failed')
      do i=1,n
        if (a(i)/=b(i)) then
          write(*,'(a,i0)') trim(label)//' first differing byte offset: ',offset+int(i-1,int64)
          error stop 1
        end if
      end do
      offset=offset+n64
    end do
    close(ru); close(nu)
  end subroutine compare_bytes
end program verify_real_full_domain
