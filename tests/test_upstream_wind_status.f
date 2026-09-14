c     Controlled external routines for the upstream OpenMP wind status test.
c     This is fixed form and deliberately contains no real wind producer.

      logical function wind_case_is(name)
      implicit none
      character*(*) name
      character*64 case_name
      integer n,istat

      case_name = ' '
      call get_environment_variable('UPSTREAM_WIND_CASE',
     1     case_name,n,istat)
      if(istat .ne. 0 .or. n .le. 0) case_name = 'full'
      wind_case_is = trim(case_name) .eq. trim(name)
      return
      end

      subroutine set_post_status(vert_status,writer_status)
      implicit none
      integer vert_status,writer_status
      integer post_vert_status,post_writer_status,post_writer_calls
      common /wind_post_control/ post_vert_status,post_writer_status,
     1     post_writer_calls

      post_vert_status = vert_status
      post_writer_status = writer_status
      post_writer_calls = 0
      return
      end

      subroutine vert_wind(uanl,vanl,uanl_sfc,vanl_sfc,nx,ny,nz,
     1     wanl,topo,lat,lon,spacing,rk_terrain,
     2     r_missing,l_grid,istatus)
      implicit none
      integer nx,ny,nz,istatus
      real uanl(nx,ny,nz),vanl(nx,ny,nz)
      real uanl_sfc(nx,ny),vanl_sfc(nx,ny)
      real wanl(nx,ny,nz),topo(nx,ny),lat(nx,ny),lon(nx,ny)
      real rk_terrain(nx,ny),spacing,r_missing
      logical l_grid
      integer post_vert_status,post_writer_status,post_writer_calls
      common /wind_post_control/ post_vert_status,post_writer_status,
     1     post_writer_calls

      wanl = 0.0
      istatus = post_vert_status
      return
      end

      subroutine put_laps_multi_3d_jacket(i4time,ext,var_3d,units_3d,
     1     comment_3d,uanl,vanl,wanl,nx,ny,nz,nfields,istatus)
      implicit none
      integer i4time,nx,ny,nz,nfields,istatus
      character*3 ext,var_3d(nfields)
      character*10 units_3d(nfields)
      character*125 comment_3d(nfields)
      real uanl(nx,ny,nz),vanl(nx,ny,nz),wanl(nx,ny,nz)
      integer post_vert_status,post_writer_status,post_writer_calls
      common /wind_post_control/ post_vert_status,post_writer_status,
     1     post_writer_calls

      post_writer_calls = post_writer_calls + 1
      istatus = post_writer_status
      return
      end

      integer function ishow_timer()
      implicit none
      ishow_timer = 0
      return
      end

      subroutine get_grid_dim_xy(nx,ny,istatus)
      implicit none
      integer nx,ny,istatus
      logical wind_case_is
      external wind_case_is

      nx = 2
      ny = 3
      istatus = 1
      if(wind_case_is('grid_failure')) istatus = 0
      if(wind_case_is('invalid_x')) nx = 0
      if(wind_case_is('invalid_y')) ny = 0
      return
      end

      subroutine get_laps_dimensions(nz,istatus)
      implicit none
      integer nz,istatus
      logical wind_case_is
      external wind_case_is

      nz = 2
      istatus = 1
      if(wind_case_is('dim_failure')) istatus = 0
      if(wind_case_is('invalid_z')) nz = 0
      return
      end

      subroutine get_systime(i4time,a9_time,istatus)
      implicit none
      integer i4time,istatus
      character*9 a9_time
      logical wind_case_is
      external wind_case_is

      i4time = 123456789
      a9_time = '123456789'
      istatus = 1
      if(wind_case_is('time_failure')) istatus = 0
      return
      end

      subroutine get_directory(ext,directory,length)
      implicit none
      character*(*) ext,directory
      integer length,n,istat
      logical wind_case_is
      external wind_case_is

      if(wind_case_is('logunset')) return
      directory = ' '
      call get_environment_variable('UPSTREAM_WIND_LOG_DIR',
     1     directory,n,istat)
      if(istat .ne. 0 .or. n .le. 0) then
        length = 0
        return
      endif
      length = min(n,len(directory))
      if(directory(length:length) .ne. '/') then
        length = length + 1
        directory(length:length) = '/'
      endif
      return
      end

      subroutine get_max_radars(max_radars,istatus)
      implicit none
      integer max_radars,istatus
      logical wind_case_is
      external wind_case_is

      max_radars = 2
      istatus = 1
      if(wind_case_is('zero_radars')) max_radars = 0
      if(wind_case_is('negative_radars')) max_radars = -1
      if(wind_case_is('maxradars_failure')) istatus = 0
      return
      end

      subroutine get_meso_sao_pirep(n_meso,n_sao,n_pirep,istatus)
      implicit none
      integer n_meso,n_sao,n_pirep,istatus
      logical wind_case_is
      external wind_case_is

      n_meso = 0
      n_sao = 0
      n_pirep = 0
      istatus = 1
      if(wind_case_is('negative_metadata')) n_meso = -1
      if(wind_case_is('obs_failure')) istatus = 0
      return
      end

      subroutine get_r_missing_data(r_missing_data,istatus)
      implicit none
      real r_missing_data
      integer istatus
      logical wind_case_is
      external wind_case_is

      r_missing_data = -9999.0
      istatus = 1
      if(wind_case_is('missing_failure')) istatus = 0
      return
      end

      subroutine get_i2_missing_data(i2_missing_data,istatus)
      implicit none
      integer i2_missing_data,istatus
      logical wind_case_is
      external wind_case_is

      i2_missing_data = -9999
      istatus = 1
      if(wind_case_is('i2_missing_failure')) istatus = 0
      return
      end

      subroutine lapswind_anal(i4time,nx,ny,nz,ntmin,ntmax,
     1     max_radars,n_meso,n_sao,n_pirep,r_missing_data,
     2     i2_missing_data,n_prods_out,i4time_array,j_status)
      implicit none
      integer i4time,nx,ny,nz,ntmin,ntmax,max_radars
      integer n_meso,n_sao,n_pirep,i2_missing_data,n_prods_out
      integer i4time_array(20),j_status(20)
      real r_missing_data
      logical wind_case_is
      external wind_case_is

      write(6,'(A)') 'WIND_STUB_ENTERED'
      write(15,'(A)') 'WIND_STUB_LOG'
      if(wind_case_is('untouched')) return

      n_prods_out = 1
      j_status(6) = 1
      i4time_array(6) = i4time
      if(wind_case_is('lwm_only')) then
        j_status(6) = 3
        j_status(7) = 1
      else if(wind_case_is('wrong_time')) then
        i4time_array(6) = i4time + 1
      else if(wind_case_is('no_products')) then
        n_prods_out = 0
      else if(wind_case_is('full')) then
        j_status(7) = 1
      endif
      return
      end

      program wind_status_test
      implicit none
      integer failures

      failures = 0
      call check_post(0,1,0,0,failures)
      call check_post(1,1,1,1,failures)
      call check_post(1,0,0,1,failures)
      call check_post(1,2,2,1,failures)
      if(failures .ne. 0) stop 1
      write(6,'(A)') 'UPSTREAM_WIND_POST_TEST_PASS'
      end

      subroutine check_post(vert_status,writer_status,expected_status,
     1     expected_calls,failures)
      implicit none
      integer vert_status,writer_status,expected_status,expected_calls
      integer failures,istat_lw3
      integer nx,ny,nz,nfields
      real uanl(2,3,2),vanl(2,3,2),uanl_sfc(2,3),vanl_sfc(2,3)
      real topo(2,3),lat(2,3),lon(2,3),rk_terrain(2,3)
      real spacing,r_missing
      character*3 ext,var_3d(3)
      character*10 units_3d(3)
      character*125 comment_3d(3)
      logical l_grid
      integer post_vert_status,post_writer_status,post_writer_calls
      common /wind_post_control/ post_vert_status,post_writer_status,
     1     post_writer_calls

      nx = 2
      ny = 3
      nz = 2
      nfields = 3
      uanl = 1.0
      vanl = 2.0
      uanl_sfc = 1.0
      vanl_sfc = 2.0
      topo = 0.0
      lat = 0.0
      lon = 0.0
      rk_terrain = 0.0
      spacing = 1000.0
      r_missing = -9999.0
      ext = 'lw3'
      var_3d = '   '
      units_3d = '          '
      comment_3d = ' '
      l_grid = .false.
      istat_lw3 = 1
      call set_post_status(vert_status,writer_status)
      call wind_post_process(123456789,ext,var_3d,units_3d,comment_3d,
     1     uanl,vanl,nx,ny,nz,nfields,uanl_sfc,vanl_sfc,topo,lat,lon,
     2     spacing,rk_terrain,r_missing,l_grid,istat_lw3)
      if(istat_lw3 .ne. expected_status .or.
     1   post_writer_calls .ne. expected_calls) then
        write(6,'(A,2(1X,I0))') 'BAD_WIND_POST_STATUS',vert_status,
     1     writer_status
        failures = failures + 1
      endif
      return
      end
