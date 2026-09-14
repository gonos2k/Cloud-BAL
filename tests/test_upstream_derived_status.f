c     Controlled external routines and writer harness for the upstream
c     derived-product status test.  This file is fixed form deliberately.

      logical function derived_case_is(name)
      implicit none
      character*(*) name
      character*64 case_name
      integer n,istat

      case_name = ' '
      call get_environment_variable('UPSTREAM_DERIVED_CASE',
     1     case_name,n,istat)
      if(istat .ne. 0 .or. n .le. 0) case_name = 'full_success'
      derived_case_is = trim(case_name) .eq. trim(name)
      return
      end

      subroutine get_systime(i4time,a9_time,istatus)
      implicit none
      integer i4time,istatus
      character*9 a9_time
      logical derived_case_is
      external derived_case_is

      i4time = 123456789
      a9_time = '123456789'
      istatus = 1
      if(derived_case_is('time_failure')) istatus = 0
      return
      end

      subroutine get_grid_dim_xy(nx,ny,istatus)
      implicit none
      integer nx,ny,istatus
      logical derived_case_is
      external derived_case_is

      nx = 2
      ny = 3
      istatus = 1
      if(derived_case_is('grid_failure')) istatus = 0
      if(derived_case_is('invalid_x')) nx = 0
      if(derived_case_is('invalid_y')) ny = 0
      return
      end

      subroutine get_laps_dimensions(nz,istatus)
      implicit none
      integer nz,istatus
      logical derived_case_is
      external derived_case_is

      nz = 2
      istatus = 1
      if(derived_case_is('dim_failure')) istatus = 0
      if(derived_case_is('invalid_z')) nz = 0
      return
      end

      subroutine get_r_missing_data(r_missing_data,istatus)
      implicit none
      real r_missing_data
      integer istatus
      logical derived_case_is
      external derived_case_is

      r_missing_data = -9999.0
      istatus = 1
      if(derived_case_is('missing_failure')) istatus = 0
      return
      end

      subroutine laps_deriv(i4time,nx,ny,nz,r_missing_data,j_status)
      implicit none
      integer i4time,nx,ny,nz,j_status(20)
      real r_missing_data
      logical derived_case_is
      external derived_case_is

      write(6,'(A)') 'LCO_STUB_ENTERED'
      if(derived_case_is('untouched')) return
      if(derived_case_is('other_success')) then
        j_status(1) = 1
      else if(derived_case_is('lco_failure')) then
        j_status(10) = 4
      else if(derived_case_is('lco_only')) then
        j_status(10) = 1
      else if(derived_case_is('full_success')) then
        j_status = 1
      endif
      return
      end

      subroutine set_writer_status(status)
      implicit none
      integer status
      integer writer_status_value,writer_calls,timer_calls
      integer writer_metadata_ok,writer_layout_ok
      common /derived_writer_control/ writer_status_value,writer_calls,
     1     timer_calls,writer_metadata_ok,writer_layout_ok

      writer_status_value = status
      writer_calls = 0
      timer_calls = 0
      writer_metadata_ok = 0
      writer_layout_ok = 0
      return
      end

      subroutine put_laps_multi_3d(i4time,ext,variable,units,comment,
     1     field_3d,nx,ny,nz,nfield,istatus)
      implicit none
      integer i4time,nx,ny,nz,nfield,istatus
      character*31 ext
      character*3 variable(nfield)
      character*10 units(nfield)
      character*125 comment(nfield)
      real field_3d(nx,ny,nz,nfield)
      integer writer_status_value,writer_calls,timer_calls
      integer writer_metadata_ok,writer_layout_ok
      common /derived_writer_control/ writer_status_value,writer_calls,
     1     timer_calls,writer_metadata_ok,writer_layout_ok
      integer i,j,k
      real expected

      writer_calls = writer_calls + 1
      writer_metadata_ok = 0
      if(i4time .eq. 123456789 .and. trim(ext) .eq. 'lco' .and.
     1   nx .eq. 2 .and. ny .eq. 3 .and. nz .eq. 2 .and.
     2   nfield .eq. 1 .and. trim(variable(1)) .eq. 'COM' .and.
     3   trim(units(1)) .eq. 'PA/S' .and.
     4   trim(comment(1)) .eq. 'LAPS Cloud Derived Omega') then
        writer_metadata_ok = 1
      endif

      writer_layout_ok = 1
      do k = 1,nz
        do j = 1,ny
          do i = 1,nx
            expected = 100.0*real(i) + 10.0*real(j) + real(k)
            if(field_3d(i,j,k,1) .ne. expected) writer_layout_ok = 0
          enddo
        enddo
      enddo
      istatus = writer_status_value
      return
      end

      integer function ishow_timer()
      implicit none
      integer writer_status_value,writer_calls,timer_calls
      integer writer_metadata_ok,writer_layout_ok
      common /derived_writer_control/ writer_status_value,writer_calls,
     1     timer_calls,writer_metadata_ok,writer_layout_ok

      timer_calls = timer_calls + 1
      ishow_timer = 0
      return
      end

      program test_upstream_derived_writer
      implicit none
      integer failures

      failures = 0
      call check_writer(-1,4,0,failures)
      call check_writer(0,4,0,failures)
      call check_writer(1,1,1,failures)
      call check_writer(2,4,0,failures)
      if(failures .ne. 0) stop 1
      write(6,'(A)') 'UPSTREAM_DERIVED_WRITER_TEST_PASS'
      end

      subroutine check_writer(requested_status,expected_status,
     1     expected_timer,failures)
      implicit none
      integer requested_status,expected_status,expected_timer,failures
      integer observed_status,observed_calls,observed_timer
      integer metadata_ok,layout_ok
      external lco_writer_probe

      call lco_writer_probe(requested_status,observed_status,
     1     observed_calls,observed_timer,metadata_ok,layout_ok)
      if(observed_status .ne. expected_status .or.
     1   observed_calls .ne. 1 .or.
     2   observed_timer .ne. expected_timer .or.
     3   metadata_ok .ne. 1 .or. layout_ok .ne. 1) then
        write(6,'(A,1X,I0)') 'BAD_LCO_WRITER_STATUS',requested_status
        failures = failures + 1
      endif
      return
      end
