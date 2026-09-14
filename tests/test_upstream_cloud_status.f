c     Controlled interfaces for the upstream cloud status and writer tests.
c     Fixed form is intentional; no operational cloud science is linked.

      logical function cloud_case_is(name)
      implicit none
      character*(*) name
      character*64 case_name
      integer n,istat

      case_name = ' '
      call get_environment_variable('UPSTREAM_CLOUD_CASE',
     1     case_name,n,istat)
      if(istat .ne. 0 .or. n .le. 0) case_name = 'full_success'
      cloud_case_is = trim(case_name) .eq. trim(name)
      return
      end

      subroutine get_systime(i4time,a9_time,istatus)
      implicit none
      integer i4time,istatus
      character*9 a9_time
      logical cloud_case_is
      external cloud_case_is

      i4time = 123456789
      a9_time = '123456789'
      istatus = 1
      if(cloud_case_is('time_failure')) istatus = 0
      return
      end

      subroutine get_grid_dim_xy(nx,ny,istatus)
      implicit none
      integer nx,ny,istatus
      logical cloud_case_is
      external cloud_case_is

      nx = 2
      ny = 3
      istatus = 1
      if(cloud_case_is('grid_failure')) istatus = 0
      if(cloud_case_is('invalid_x')) nx = 0
      if(cloud_case_is('invalid_y')) ny = 0
      return
      end

      subroutine get_laps_dimensions(nz,istatus)
      implicit none
      integer nz,istatus
      logical cloud_case_is
      external cloud_case_is

      nz = 2
      istatus = 1
      if(cloud_case_is('dim_failure')) istatus = 0
      if(cloud_case_is('invalid_z')) nz = 0
      return
      end

      subroutine get_meso_sao_pirep(n_meso,n_sao,n_pirep,istatus)
      implicit none
      integer n_meso,n_sao,n_pirep,istatus
      logical cloud_case_is
      external cloud_case_is

      n_meso = 0
      n_sao = 0
      n_pirep = 2
      istatus = 1
      if(cloud_case_is('pirep_failure')) istatus = 0
      if(cloud_case_is('negative_pirep')) n_pirep = -1
      if(cloud_case_is('zero_pirep')) n_pirep = 0
      if(cloud_case_is('sum_overflow')) n_pirep = 1
      return
      end

      subroutine get_maxstns(maxstns,istatus)
      implicit none
      integer maxstns,istatus
      logical cloud_case_is
      external cloud_case_is

      maxstns = 4
      istatus = 1
      if(cloud_case_is('maxstns_failure')) istatus = 0
      if(cloud_case_is('zero_maxstns')) maxstns = 0
      if(cloud_case_is('sum_overflow')) maxstns = 2147483647
      return
      end

      subroutine laps_cloud(i4time,nx,ny,nz,n_pirep,maxstns,
     1     max_cld_snd,i_diag,n_prods,iprod_number,isplit,j_status)
      implicit none
      integer i4time,nx,ny,nz,n_pirep,maxstns,max_cld_snd
      integer i_diag,n_prods,iprod_number(20),isplit,j_status(20)
      logical cloud_case_is
      external cloud_case_is

      write(6,'(A)') 'CLOUD_STUB_ENTERED'
      if(cloud_case_is('untouched')) return
      if(cloud_case_is('only_lc3')) then
        j_status(1) = 1
      else if(cloud_case_is('only_lcb')) then
        j_status(3) = 1
      else if(cloud_case_is('only_lcv')) then
        j_status(4) = 1
      else if(cloud_case_is('optional_only')) then
        j_status(2) = 1
      else if(cloud_case_is('required_triple')) then
        j_status(1) = 1
        j_status(3) = 1
        j_status(4) = 1
      else if(cloud_case_is('full_success') .or.
     1        cloud_case_is('zero_pirep')) then
        j_status = 1
      else if(cloud_case_is('missing_lc3')) then
        j_status(1) = 3
        j_status(3) = 1
        j_status(4) = 1
      else if(cloud_case_is('missing_lcb')) then
        j_status(1) = 1
        j_status(3) = 3
        j_status(4) = 1
      else if(cloud_case_is('missing_lcv')) then
        j_status(1) = 1
        j_status(3) = 1
        j_status(4) = 3
      endif
      return
      end

      subroutine set_cloud_writer_status(status)
      implicit none
      integer status
      integer cloud_writer_status,cloud_writer_calls,cloud_writer_ok
      common /cloud_writer_control/ cloud_writer_status,
     1     cloud_writer_calls,cloud_writer_ok

      cloud_writer_status = status
      cloud_writer_calls = 0
      cloud_writer_ok = 0
      return
      end

      subroutine get_directory(ext,directory,length)
      implicit none
      character*(*) ext,directory
      integer length

      directory = '/controlled/cloud/'
      length = len_trim(directory)
      return
      end

      subroutine write_laps_data(i4time,directory,ext,imax,jmax,
     1     kmax,kdim,var,lvl,lvl_coord,units,comment,data,istatus)
      implicit none
      integer i4time,imax,jmax,kmax,kdim,lvl(kdim),istatus
      character*(*) directory,ext
      character*3 var(kdim)
      character*4 lvl_coord(kdim)
      character*10 units(kdim)
      character*125 comment(kdim)
      real data(imax,jmax,kdim)
      integer cloud_writer_status,cloud_writer_calls,cloud_writer_ok
      common /cloud_writer_control/ cloud_writer_status,
     1     cloud_writer_calls,cloud_writer_ok
      integer i,j,k
      real expected
      character*125 expected_comment

      cloud_writer_calls = cloud_writer_calls + 1
      cloud_writer_ok = 0
      if(i4time .ne. 123456789 .or. trim(ext) .ne. 'lc3' .or.
     1   imax .ne. 2 .or. jmax .ne. 3 .or. kmax .ne. kdim)
     2   go to 100
      do k = 1,kdim
        write(expected_comment,10) 1000.0*real(k),900.0-real(k)
10      format(2e20.8,' Height MSL, Pressure')
        if(trim(var(k)) .ne. 'LC3' .or.
     1     lvl(k) .ne. k .or. trim(lvl_coord(k)) .ne. 'MSL' .or.
     2     trim(units(k)) .ne. 'Fractional' .or.
     3     trim(comment(k)) .ne. trim(expected_comment)) go to 100
        do j = 1,jmax
          do i = 1,imax
            expected = 100.0*real(i)+10.0*real(j)+real(k)
            if(data(i,j,k) .ne. expected) go to 100
          enddo
        enddo
      enddo
      cloud_writer_ok = 1
100   istatus = cloud_writer_status
      return
      end

      program test_upstream_cloud_writer
      implicit none
      integer failures

      failures = 0
      call check_writer_status(0,failures)
      call check_writer_status(1,failures)
      call check_writer_status(2,failures)
      call check_writer_case(42,1,failures)
      call check_nk_guard(0,failures)
      call check_nk_guard(43,failures)
      call check_dim_guard(0,3,failures)
      call check_dim_guard(2,0,failures)
      if(failures .ne. 0) stop 1
      write(6,'(A)') 'UPSTREAM_CLOUD_WRITER_TEST_PASS'
      end

      subroutine check_writer_status(requested_status,failures)
      implicit none
      integer requested_status,failures
      call check_writer_case(1,requested_status,failures)
      return
      end

      subroutine check_writer_case(nk,requested_status,failures)
      implicit none
      integer nk,requested_status,failures
      integer observed_status,observed_calls,metadata_ok
      external cloud_writer_probe

      call cloud_writer_probe(nk,2,3,requested_status,observed_status,
     1     observed_calls,metadata_ok)
      if(observed_status .ne. requested_status .or.
     1   observed_calls .ne. 1 .or. metadata_ok .ne. 1) then
        write(6,'(A,1X,I0)') 'BAD_CLOUD_WRITER_STATUS',requested_status
        failures = failures + 1
      endif
      return
      end

      subroutine check_nk_guard(nk,failures)
      implicit none
      integer nk,failures
      integer observed_status,observed_calls,metadata_ok
      external cloud_writer_probe

      call cloud_writer_probe(nk,2,3,1,observed_status,
     1     observed_calls,metadata_ok)
      if(observed_status .eq. 1 .or. observed_calls .ne. 0) then
        write(6,'(A,1X,I0)') 'BAD_CLOUD_NK_GUARD',nk
        failures = failures + 1
      endif
      return
      end

      subroutine check_dim_guard(ni,nj,failures)
      implicit none
      integer ni,nj,failures
      integer observed_status,observed_calls,metadata_ok
      external cloud_writer_probe

      call cloud_writer_probe(1,ni,nj,1,observed_status,
     1     observed_calls,metadata_ok)
      if(observed_status .eq. 1 .or. observed_calls .ne. 0) then
        write(6,'(A,2(1X,I0))') 'BAD_CLOUD_DIM_GUARD',ni,nj
        failures = failures + 1
      endif
      return
      end
