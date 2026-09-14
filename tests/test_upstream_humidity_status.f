c     Controlled external routines for the upstream humidity status test.
c     This file is fixed form on purpose.  It does not provide a main program:
c     the executable is the real lq3driver overlay plus these stubs only.

      logical function humidity_case_is(name)
      implicit none
      character*(*) name
      character*64 case_name
      integer n,istat

      case_name = ' '
      call get_environment_variable('UPSTREAM_HUMIDITY_CASE',
     1     case_name,n,istat)
      if(istat .ne. 0 .or. n .le. 0) case_name = 'fullsuccess'
      humidity_case_is = trim(case_name) .eq. trim(name)
      return
      end

      subroutine get_laps_config(grid_name,istatus)
      implicit none
      character*(*) grid_name
      integer istatus
      include 'lapsparms.cmn'
      logical humidity_case_is
      external humidity_case_is

      grid_name = 'nest7grid'
      nx_l_cmn = 2
      ny_l_cmn = 2
      nk_laps = 2
      laps_cycle_time_cmn = 3600
      r_missing_data_cmn = -9999.0
      istatus = 1
      if(humidity_case_is('configbad')) istatus = 0
      if(humidity_case_is('griddim0')) nx_l_cmn = 0
      if(humidity_case_is('cycle0')) laps_cycle_time_cmn = 0
      return
      end

      subroutine get_directory(ext_in,directory_out,len_dir)
      implicit none
      character*(*) ext_in,directory_out
      integer len_dir,n,istat

      directory_out = ' '
      call get_environment_variable('UPSTREAM_HUMIDITY_INPUT_DIR',
     1     directory_out,n,istat)
      if(istat .ne. 0 .or. n .le. 0) then
        len_dir = 0
        return
      endif
      len_dir = min(n,len(directory_out))
      if(len_dir .lt. len(directory_out)) then
        if(directory_out(len_dir:len_dir) .ne. '/') then
          len_dir = len_dir + 1
          directory_out(len_dir:len_dir) = '/'
        endif
      endif
      return
      end

      subroutine i4time_fname_lp(fname_in,i4time,istatus)
      implicit none
      character*(*) fname_in
      integer i4time,istatus,ios
      logical humidity_case_is
      external humidity_case_is

      i4time = 123456789
      istatus = 1
      if(humidity_case_is('parsefail')) then
        istatus = 0
      else if(humidity_case_is('timemismatch')) then
        i4time = 123456788
      else
        read(fname_in,'(i9)',iostat=ios) i4time
        if(ios .ne. 0) then
          i4time = 0
          istatus = 0
        endif
      endif
      return
      end

      subroutine lq3_driver1a(i4time,ii,jj,kk,mdf,lct,jstatus)
      implicit none
      integer i4time,ii,jj,kk,lct,jstatus(3)
      real mdf
      logical humidity_case_is
      external humidity_case_is

      write(6,'(A)') 'LQ3_STUB_ENTERED'
      if(humidity_case_is('untouchedjstatus')) return
      jstatus(1) = 0
      jstatus(2) = 0
      jstatus(3) = 0
      if(humidity_case_is('onlyLH3')) then
        jstatus(2) = 1
      else if(humidity_case_is('onlyLH4')) then
        jstatus(3) = 1
      else if(humidity_case_is('lq3only')) then
        jstatus(1) = 1
      else if(humidity_case_is('fullsuccess')) then
        jstatus(1) = 1
        jstatus(2) = 1
        jstatus(3) = 1
      endif
      return
      end
