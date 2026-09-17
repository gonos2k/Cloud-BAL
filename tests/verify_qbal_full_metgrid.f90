program verify_qbal_full_metgrid
  use iso_fortran_env, only: int32, real64
  use ieee_arithmetic, only: ieee_is_finite
  use qbal_metgrid_wind_reference, only: reference_winds
  use netcdf
  implicit none
  character(1024) :: wps_path, geo_path, met_path
  character(19), parameter :: valid_time='2023-05-18_03:33:20'
  character(3), parameter :: names(5)=[character(3)::'TT','UU','VV','QV','GHT']
  real, parameter :: levels(5)=[200100.,100000.,90000.,80000.,70000.]
  real :: source(6,6,5,5), surface_pressure(6,6)
  real, allocatable :: actual(:,:,:), expected(:,:,:), geo(:,:,:)
  integer :: met, grid, field, k, i, j

  if (command_argument_count()/=3) call fail('usage: verify_qbal_full_metgrid WPS GEO MET_EM')
  call get_command_argument(1,wps_path)
  call get_command_argument(2,geo_path)
  call get_command_argument(3,met_path)
  call read_wps()
  call nc(nf90_open(trim(geo_path),nf90_nowrite,grid))
  call nc(nf90_open(trim(met_path),nf90_nowrite,met))
  call check_time()
  call check_geometry()
  do field=1,5
    if (field==2.or.field==3) cycle ! Wind reference is checked separately below.
    call read_field(met,trim(names(field)),4,4,5,actual)
    allocate(expected(4,4,5))
    do k=1,5
      do j=1,4
        do i=1,4
          ! check_geometry verifies these nearest source indices from the
          ! actual target coordinates and the source projection.
          expected(i,j,k)=source(i+1,j+1,k,field)
        end do
      end do
    end do
    call compare(actual,expected,trim(names(field)),0.)
    deallocate(actual,expected)
  end do
  call read_field(met,'PRES',4,4,5,actual)
  allocate(expected(4,4,5))
  expected(:,:,1)=surface_pressure(2:5,2:5)
  do k=2,5
    expected(:,:,k)=levels(k)
  end do
  call compare(actual,expected,'PRES',0.)
  deallocate(actual,expected)
  call check_winds()
  call nc(nf90_close(met))
  call nc(nf90_close(grid))
  print '(a)', 'PASS_SCOPED: full metgrid exact time, nearest-neighbor fields and target geometry'
contains
  subroutine fail(message)
    character(*), intent(in) :: message
    print '(a)', 'FAIL: '//trim(message)
    error stop 1
  end subroutine

  subroutine nc(status)
    integer, intent(in) :: status
    if (status/=nf90_noerr) call fail(nf90_strerror(status))
  end subroutine

  subroutine check_time()
    character(19) :: times(1), start
    integer :: var, dim, length
    call nc(nf90_inq_dimid(met,'Time',dim))
    call nc(nf90_inquire_dimension(met,dim,len=length))
    if (length/=1) call fail('met_em Time dimension')
    call nc(nf90_inq_dimid(met,'DateStrLen',dim))
    call nc(nf90_inquire_dimension(met,dim,len=length))
    if (length/=19) call fail('met_em DateStrLen')
    call nc(nf90_inq_varid(met,'Times',var))
    call nc(nf90_get_var(met,var,times))
    if (times(1)/=valid_time) call fail('met_em exact time mismatch')
    call nc(nf90_get_att(met,nf90_global,'SIMULATION_START_DATE',start))
    if (start/=valid_time) call fail('met_em start time mismatch')
  end subroutine

  subroutine read_field(file,name,nx,ny,nz,values)
    integer, intent(in) :: file,nx,ny,nz
    character(*), intent(in) :: name
    real, allocatable, intent(out) :: values(:,:,:)
    integer :: var,rank,kind,dims(4),length,d,shape_expected(4)
    character(32) :: dimension_name,expected_name
    character(25) :: unit_text,expected_units
    character :: stagger,expected_stagger
    call nc(nf90_inq_varid(file,name,var))
    call nc(nf90_inquire_variable(file,var,xtype=kind,ndims=rank))
    if (kind/=nf90_float.or.rank<3.or.rank>4) call fail(name//' schema mismatch')
    if (nz>1.and.rank/=4) call fail(name//' vertical dimension missing')
    call nc(nf90_inquire_variable(file,var,dimids=dims(:rank)))
    shape_expected=[nx,ny,1,1]
    if (rank==4) shape_expected(3)=nz
    do d=1,rank
      call nc(nf90_inquire_dimension(file,dims(d),len=length))
      if (length/=shape_expected(d)) call fail(name//' shape mismatch')
      call nc(nf90_inquire_dimension(file,dims(d),name=dimension_name))
      select case(d)
      case(1)
        expected_name='west_east'
        if (nx==5) expected_name='west_east_stag'
      case(2)
        expected_name='south_north'
        if (ny==5) expected_name='south_north_stag'
      case(3)
        expected_name='Time'
        if (rank==4) expected_name='num_metgrid_levels'
      case(4)
        expected_name='Time'
      end select
      if (dimension_name/=expected_name) call fail(name//' dimension meaning mismatch')
    end do
    expected_stagger='M'
    if (nx==5) expected_stagger='U'
    if (ny==5) expected_stagger='V'
    call nc(nf90_get_att(file,var,'stagger',stagger))
    if (stagger/=expected_stagger) call fail(name//' stagger mismatch')
    expected_units=''
    select case(name)
    case('TT'); expected_units='K'
    case('UU','VV'); expected_units='m s{-1}'
    case('QV'); expected_units='kg kg{-1}'
    case('GHT'); expected_units='m'
    case('XLAT_M','XLAT_U','XLAT_V'); expected_units='degrees latitude'
    case('XLONG_M','XLONG_U','XLONG_V'); expected_units='degrees longitude'
    end select
    if (len_trim(expected_units)>0.or.name=='PRES') then
      unit_text=''
      call nc(nf90_get_att(file,var,'units',unit_text))
      if (name=='PRES'.and.unit_text(1:1)==achar(0)) unit_text(1:1)=' '
      if (unit_text/=expected_units) call fail(name//' units mismatch')
    end if
    allocate(values(nx,ny,nz))
    call nc(nf90_get_var(file,var,values))
    if (.not.all(ieee_is_finite(values))) call fail(name//' nonfinite')
  end subroutine

  subroutine compare(values,reference,label,tolerance)
    real, intent(in) :: values(:,:,:),reference(:,:,:),tolerance
    character(*), intent(in) :: label
    integer :: x,y,z
    do z=1,size(values,3)
      do y=1,size(values,2)
        do x=1,size(values,1)
          if (tolerance==0.) then
            if (transfer(values(x,y,z),0_int32)/=transfer(reference(x,y,z),0_int32)) &
              call fail(label//' value mismatch')
          else
            if (abs(values(x,y,z)-reference(x,y,z))>tolerance) call fail(label//' value mismatch')
          end if
        end do
      end do
    end do
  end subroutine

  subroutine check_geometry()
    character(7), parameter :: fields(6)=[character(7)::'XLAT_M','XLONG_M','XLAT_U','XLONG_U','XLAT_V','XLONG_V']
    character(9), parameter :: attrs(9)=[character(9)::'DX','DY','CEN_LAT','CEN_LON','TRUELAT1', &
      'TRUELAT2','STAND_LON','POLE_LAT','POLE_LON']
    real :: a,b
    real(real64) :: x,y,lat,lon,source_x,source_y
    integer :: ix,iy
    integer :: n,nx,ny,projection
    do n=1,size(fields)
      nx=4; ny=4
      if (n==3.or.n==4) nx=5
      if (n==5.or.n==6) ny=5
      call read_field(grid,trim(fields(n)),nx,ny,1,geo)
      call read_field(met,trim(fields(n)),nx,ny,1,actual)
      if (mod(n,2)==0) call read_field(grid,trim(fields(n-1)),nx,ny,1,expected)
      do iy=1,ny
        do ix=1,nx
          x=real(ix,real64)+1.2_real64
          y=real(iy,real64)+1.2_real64
          if (nx==5) x=x-0.5_real64
          if (ny==5) y=y-0.5_real64
          call target_coordinate(x,y,lat,lon)
          if (mod(n,2)==1) then
            call compare_coordinate(geo(ix,iy,1),lat)
          else
            call compare_coordinate(geo(ix,iy,1),lon)
          end if
          if (mod(n,2)==0) then
            call source_coordinate(real(expected(ix,iy,1),real64),real(geo(ix,iy,1),real64),source_x,source_y)
            if (nint(source_x)/=ix+1.or.nint(source_y)/=iy+1) &
              call fail('target/source nearest-neighbor mapping mismatch')
          end if
        end do
      end do
      call compare(actual,geo,trim(fields(n)),0.)
      deallocate(actual,geo)
      if (allocated(expected)) deallocate(expected)
    end do
    do n=1,size(attrs)
      call nc(nf90_get_att(grid,nf90_global,trim(attrs(n)),a))
      call nc(nf90_get_att(met,nf90_global,trim(attrs(n)),b))
      if (.not.ieee_is_finite(a).or..not.ieee_is_finite(b)) call fail('met_em geometry nonfinite')
      select case(trim(attrs(n)))
      case('DX','DY')
        if (a/=10000.) call fail('target grid spacing contract')
      case('TRUELAT1','TRUELAT2')
        if (a/=45.) call fail('target standard latitude contract')
      case('STAND_LON')
        if (a/=127.) call fail('target standard longitude contract')
      case('POLE_LAT')
        if (a/=90.) call fail('target pole latitude contract')
      case('POLE_LON')
        if (a/=0.) call fail('target pole longitude contract')
      case('CEN_LAT','CEN_LON')
        call target_coordinate(3.7_real64,3.7_real64,lat,lon)
        if (attrs(n)=='CEN_LAT') call compare_coordinate(a,lat)
        if (attrs(n)=='CEN_LON') call compare_coordinate(a,lon)
      end select
      if (transfer(a,0_int32)/=transfer(b,0_int32)) call fail('met_em geometry attribute mismatch')
    end do
    call nc(nf90_get_att(grid,nf90_global,'MAP_PROJ',projection))
    if (projection/=1) call fail('target projection mismatch')
    call nc(nf90_get_att(met,nf90_global,'MAP_PROJ',projection))
    if (projection/=1) call fail('met_em projection mismatch')
  end subroutine

  subroutine target_coordinate(x,y,latitude,longitude)
    real(real64), intent(in) :: x,y
    real(real64), intent(out) :: latitude,longitude
    real(real64) :: radians,cone,rho,theta
    radians=acos(-1._real64)/180._real64
    cone=sin(45._real64*radians)
    rho=sqrt(((x-1)*10000)**2+(6370000._real64-(y-1)*10000)**2)
    theta=atan2((x-1)*10000,6370000._real64-(y-1)*10000)
    latitude=90._real64-2*atan(tan(22.5_real64*radians)*(rho/6370000._real64)**(1/cone))/radians
    longitude=127._real64+theta/(cone*radians)
  end subroutine

  subroutine compare_coordinate(value,reference)
    real, intent(in) :: value
    real(real64), intent(in) :: reference
    ! Bound single-precision projection/trigonometric evaluation; metadata
    ! transfer itself is checked bitwise separately.
    if (abs(real(value,real64)-reference)>8*epsilon(1.)*max(1._real64,abs(reference))) &
      call fail('target Lambert coordinate mismatch')
  end subroutine

  subroutine source_coordinate(latitude,longitude,x,y)
    real(real64), intent(in) :: latitude,longitude
    real(real64), intent(out) :: x,y
    real(real64) :: radians,cone,rho,theta
    radians=acos(-1._real64)/180._real64
    cone=sin(45._real64*radians)
    rho=6371229._real64*(tan((45._real64-latitude/2)*radians)/tan(22.5_real64*radians))**cone
    theta=cone*(longitude-127._real64)*radians
    x=1+rho*sin(theta)/10000
    y=1+(6371229._real64-rho*cos(theta))/10000
  end subroutine

  subroutine read_wps()
    integer :: unit,ios,version,nx,ny,projection,wind,n,f,l,count
    character(24) :: date
    character(32) :: origin
    character(9) :: name
    character(25) :: units
    character(46) :: description
    character(8) :: location
    real :: forecast,level,geometry(8),slab(6,6)
    logical :: seen(5,5),have_pressure
    seen=.false.; have_pressure=.false.; count=0
    open(newunit=unit,file=trim(wps_path),status='old',form='unformatted', &
      access='sequential',action='read',convert='little_endian',iostat=ios)
    if (ios/=0) call fail('approved WPS open')
    do
      read(unit,iostat=ios) version
      if (ios<0) exit
      if (ios/=0.or.version/=5) call fail('WPS version')
      read(unit,iostat=ios) date,forecast,origin,name,units,description,level,nx,ny,projection
      if (ios/=0) call fail('WPS header')
      if (date/=valid_time//'.0000'.or.forecast/=0.) call fail('approved WPS time')
      if (nx/=6.or.ny/=6.or.projection/=3) call fail('approved WPS geometry shape')
      read(unit,iostat=ios) location,geometry
      if (ios/=0) call fail('WPS geometry')
      if (location/='SWCORNER'.or.any(geometry/=[45.,127.,10.,10.,127.,45.,45.,6371.229])) &
        call fail('approved WPS base geometry')
      read(unit,iostat=ios) wind
      if (ios/=0.or.wind==0) call fail('approved WPS wind basis')
      read(unit,iostat=ios) slab
      if (ios/=0) call fail('WPS slab')
      if (.not.all(ieee_is_finite(slab))) call fail('WPS nonfinite')
      count=count+1
      if (name=='PSFC') then
        if (have_pressure.or.level/=200100.) call fail('WPS PSFC level')
        surface_pressure=slab; have_pressure=.true.
      end if
      if (name=='HGT') name='GHT'
      f=0; l=0
      do n=1,5
        if (name==names(n)) f=n
        if (level==levels(n)) l=n
      end do
      if (f==0) cycle
      if (l==0) call fail('WPS field level')
      if (seen(l,f)) call fail('WPS duplicate field')
      source(:,:,l,f)=slab; seen(l,f)=.true.
    end do
    close(unit)
    if (count/=33.or..not.all(seen).or..not.have_pressure) call fail('WPS required records')
  end subroutine

  subroutine check_winds()
    real :: expect_u(5,4),expect_v(4,5),tolerance
    real, allocatable :: lon_u(:,:,:),lon_v(:,:,:),u(:,:,:),v(:,:,:)
    real(real64) :: scale
    integer :: z
    call read_field(grid,'XLONG_U',5,4,1,lon_u)
    call read_field(grid,'XLONG_V',4,5,1,lon_v)
    call read_field(met,'UU',5,4,5,u)
    call read_field(met,'VV',4,5,5,v)
    do z=1,5
      call reference_winds(source(:,:,z,2),source(:,:,z,3), &
        lon_u(:,:,1),lon_v(:,:,1),expect_u,expect_v)
      scale=real(max(maxval(abs(source(:,:,z,2))),maxval(abs(source(:,:,z,3)))),real64)
      tolerance=real(64*epsilon(1.)*max(1._real64,scale))
      call compare(u(:,:,z:z),reshape(expect_u,[5,4,1]),'UU',tolerance)
      call compare(v(:,:,z:z),reshape(expect_v,[4,5,1]),'VV',tolerance)
    end do
    deallocate(lon_u,lon_v,u,v)
  end subroutine
end program
