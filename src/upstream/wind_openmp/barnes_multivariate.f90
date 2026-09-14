subroutine barnes_multivariate &
                           (var                                   &! Output
                           ,n_var,max_obs,obs_barnes              &! Input
                           ,imax,jmax,kmax,grid_spacing_m         &! Inputs
                           ,rep_pres_intvl                        &! Input
                           ,aerr                                  &! I/O
                           ,i4_loop_total                         &! Output
                           ,weight_3d,fnorm_dum,n_fnorm_dum       &! Inputs
                           ,l_analyze_dum,l_not_struct,rms_thresh &! Input
                           ,weight_bkg_const                      &! Input
                           ,topo,ldf,ni_stat,nj_stat              &! Input
                           ,n_obs_lvl,istatus)                    ! Outputs

      !$ use omp_lib
      implicit none
      
      integer*4 max_obs

!     ....................Declare I/O variables...............................

      integer*4 imax,jmax,kmax                                        ! Input
      integer*4 n_var                                                 ! Input

      include 'barnesob.inc'
      type (barnesob) :: obs_barnes(max_obs)                          ! Input
      type (barnesob) :: obs_barnes_buff(max_obs)                     ! Local

      real*4    var(imax,jmax,kmax,n_var)                             ! Output
      real*4, allocatable, dimension(:,:,:,:) :: var_buff             ! Local

      real*4    grid_spacing_m                                        ! Input
      real*4    rep_pres_intvl                                        ! Input

      real*4    aerr(imax,jmax,kmax,n_var)                            ! Output

      real*4    weight_3d(imax,jmax,kmax)                             ! Input
      integer*4 n_fnorm_dum                                           ! Input
      real*4    fnorm_dum                                             ! Input
      logical   l_not_struct,l_struct                                 ! Input
      logical   l_analyze_dum                                         ! Input
      real*4    rms_thresh                                            ! Input

!     Weight for Model Background. Recommended values: 0. to 1e+30.
!     This will make the output values match the background if far from obs.
!     A value of zero means this parameter is not active.
      real*4    weight_bkg_const                                      ! Input

      integer*4 n_obs_lvl(kmax)                                       ! Phaseout
      integer*4 istatus                                               ! Output
      integer*4 i4_loop_total                                         ! I/O
      
      integer*4 ni_stat, nj_stat                                      ! Input
      real*4 topo(ni_stat,nj_stat), ldf(ni_stat,nj_stat)              ! Input

!     Local variables
      integer*4 i4time_sys
      real*4 r_missing_data
      real*4 r0_barnes_max_m, r0_vert_grid
      real*4 conv_rate, time_wt, weight_total
      real*4 rtol
      integer*4 iter, n_iter, ncnt_total
      integer*4 n, i, j, k, l, ivar, nobs
      real*4 rms_obs, rms
      logical l_rms_exceeded
      integer*4 ialloc, istat_alloc
      integer*4 i4_elapsed, i4_loop_start, i4_loop_end
      real*4 pct_loop_total
      real*4 r0_barnes_max_in, r0_vert_grid_in
      real*4 time_wt_obs(max_obs)
      integer*4 istatus_local
      
      ! Function declarations
      integer*4 ishow_timer
      
      ! OpenMP variables
      integer*4 num_threads

      ialloc = 0

      l_struct = .not. l_not_struct

      write(6,*)' Subroutine barnes_multivariate..., l_struct=',l_struct      

!     vertical radius of influence in gridpoints
      r0_vert_grid = 0.9 * (5000. / rep_pres_intvl)

      call get_r_missing_data(r_missing_data,istatus)
      if(istatus .ne. 1)then
          write(6,*)' Error getting r_missing_data'
          return
      endif

      call get_systime_i4(i4time_sys,istatus)

!     OpenMP thread count is controlled by environment variable
      !$ num_threads = omp_get_max_threads()
      !$ if(.true.) write(6,*) 'OpenMP: Using',num_threads,' threads'

!     Tolerance denoting weight sum allowed for observations outside the
!     radius of influence that are omitted, divided by model background weight.
!     This represents the truncation error of the analysis increment.
      rtol = 1e-5 ! 1e-6

!     This is a buffer routine that passes variables into actual
!     barnes routine. This allows for things like dynamic memory allocation

      n_iter = 10

      if(kmax .gt. 1)then ! 3D temp/wind
          r0_barnes_max_m = 240000.
          conv_rate = 0.8
      else                ! sfc analysis
          r0_barnes_max_m = 140000.
          conv_rate = 0.5
      endif

!     This loop does multiple passes at decreasing radii
      do iter = 1,n_iter

          i4_elapsed = ishow_timer()
          i4_loop_start = i4_elapsed

          r0_barnes_max_in  = r0_barnes_max_m * conv_rate ** (iter-1)
          r0_vert_grid_in   = r0_vert_grid    * conv_rate ** (iter-1)       

          if(iter .eq. 1)then
              if(.not. l_struct)then
                  write(6,*)' code error'
                  stop
              
              else
                  ncnt_total = max_obs
                  weight_total = 0.
                  !$OMP PARALLEL DO &
                  !$OMP PRIVATE(time_wt,istatus_local)
                  do n = 1,ncnt_total
                      call get_time_wt(i4time_sys,obs_barnes(n)%i4time &
                                      ,time_wt,istatus_local)
                      time_wt_obs(n) = time_wt
                  enddo ! n
                  !$OMP END PARALLEL DO

!                 Keep the influence-radius scalar independent of thread count.
                  do n = 1,ncnt_total
                      weight_total =  weight_total &
                                   + (obs_barnes(n)%weight * time_wt_obs(n))
                  enddo
              endif

              call barnes_multivariate_sub &
                           (var                              &! Output
                           ,aerr                             &! Output
                           ,n_var,max_obs,obs_barnes         &! Input
                           ,imax,jmax,kmax,grid_spacing_m    &! Inputs
                           ,fnorm_dum,n_fnorm_dum            &! Inputs
                           ,iter,i4time_sys                  &! Input
                           ,weight_bkg_const                 &! Input
                           ,rtol,r_missing_data              &! Input
                           ,r0_barnes_max_in,r0_vert_grid_in &! Input
                           ,ncnt_total,weight_total          &! Input
                           ,time_wt_obs                      &! Input
                           ,topo,ldf,ni_stat,nj_stat         &! Input
                           ,istatus)                         ! Outputs

              i4_elapsed = ishow_timer()

!             calculate RMS
              i4_loop_end = i4_elapsed
              i4_loop_total = i4_loop_total + &
                             (i4_loop_end - i4_loop_start)
              if(i4_elapsed .gt. 0)then
                  pct_loop_total = &
                      float(i4_loop_total)/float(i4_elapsed) * 100.
              else
                  pct_loop_total = 0.
              endif
              write(6,*)'i4time loop/start/end/elapsed/% =', &
                                                 i4_loop_total, &
                                                 i4_loop_start, &
                                                 i4_loop_end,   &
                                                 i4_elapsed,    &
                                                 pct_loop_total

          elseif(iter .gt. 1)then
              if(r0_barnes_max_in .lt. 1.7 * grid_spacing_m)then
                  write(6,*)' Radius reached small criterion', &
                           ', exit iter loop ', &
                           iter,r0_barnes_max_in,grid_spacing_m
                  goto 900
              endif

!             obs_buff = obs-anal            [if iter > 1]
              !$OMP PARALLEL DO PRIVATE(i,j,k,l)
              do n = 1,ncnt_total
                  i = obs_barnes(n)%i
                  j = obs_barnes(n)%j
                  k = obs_barnes(n)%k

!                 Equate the entire structure element initially
                  obs_barnes_buff(n) = obs_barnes(n)

!                 Subtract (obs - analysis) values
                  do l = 1,n_var
                      obs_barnes_buff(n)%value(l) = &
                      obs_barnes(n)%value(l) - var(i,j,k,l)        
                  enddo ! l
              enddo ! n
              !$OMP END PARALLEL DO
              
              if(ialloc .eq. 0)then
                  allocate(var_buff(imax,jmax,kmax,n_var) &
                          ,STAT=istat_alloc)
                  if(istat_alloc .ne. 0)then
                      write(6,*)' ERROR: Could not allocate var_buff'
                      stop
                  endif
                  ialloc = 1
              endif

!             anal_buff = analyze(obs_buff)  [if iter > 1]

              call barnes_multivariate_sub &
                           (var_buff                          &! Output
                           ,aerr                              &! Output
                           ,n_var,max_obs,obs_barnes_buff     &! Input
                           ,imax,jmax,kmax,grid_spacing_m     &! Inputs
                           ,fnorm_dum,n_fnorm_dum             &! Inputs
                           ,iter,i4time_sys                   &! Input
                           ,weight_bkg_const                  &! Input
                           ,rtol,r_missing_data               &! Input
                           ,r0_barnes_max_in,r0_vert_grid_in  &! Input
                           ,ncnt_total,weight_total           &! Input
                           ,time_wt_obs                       &! Input
                           ,topo,ldf,ni_stat,nj_stat          &! Input
                           ,istatus)                          ! Output

!             anal = anal + anal_buff        [if iter > 1]
              !$OMP PARALLEL DO PRIVATE(i,j,k) COLLAPSE(3)
              do l = 1,n_var
              do k = 1,kmax
              do j = 1,jmax
                  do i = 1,imax
                      var(i,j,k,l) = var(i,j,k,l) + var_buff(i,j,k,l)
                  enddo ! i
              enddo ! j
              enddo ! k
              enddo ! l
              !$OMP END PARALLEL DO

              i4_elapsed = ishow_timer()

!             calculate RMS
              i4_loop_end = i4_elapsed
              i4_loop_total = i4_loop_total + &
                             (i4_loop_end - i4_loop_start)
              if(i4_elapsed .gt. 0)then
                  pct_loop_total = &
                      float(i4_loop_total)/float(i4_elapsed) * 100.
              else
                  pct_loop_total = 0.
              endif
              write(6,*)'i4time loop/start/end/elapsed/% =', &
                                                 i4_loop_total, &
                                                 i4_loop_start, &
                                                 i4_loop_end,   &
                                                 i4_elapsed,    &
                                                 pct_loop_total

              write(6,*)
              write(6,*)' Calculate RMS of buffer obs'

              do ivar = 1,n_var
                call get_rms_barnesobs(var_buff(1,1,1,ivar)              &! I
                      ,imax,jmax,kmax,r_missing_data,nobs                &! I/O 
                      ,n_var,ivar,max_obs,obs_barnes_buff,ncnt_total     &! I
                      ,rms_obs,rms)                                       ! O

                write(6,1)iter,ivar,nobs,rms_obs,rms

              enddo ! ivar

          endif ! iter > 1

!         calculate RMS
          write(6,*)
          write(6,*)' Calculate RMS of full obs'

          l_rms_exceeded = .false.

          do ivar = 1,n_var
              call get_rms_barnesobs(var(1,1,1,ivar)                 &! I
                      ,imax,jmax,kmax,r_missing_data,nobs            &! I/O 
                      ,n_var,ivar,max_obs,obs_barnes,ncnt_total      &! I
                      ,rms_obs,rms)                                  ! O

              write(6,1)iter,ivar,nobs,rms_obs,rms
 1            format(' iter ivar nobs rms_obs rms: ',3i6,2f10.3)

              if(rms .gt. rms_thresh)l_rms_exceeded = .true.

          enddo ! ivar

          i4_elapsed = ishow_timer()

          if(.not. l_rms_exceeded)then
              write(6,*)' RMS criterion reached, exit iter loop ', &
                       rms_thresh
              goto 900
          endif

      enddo ! iter

 900  continue

      if(ialloc .eq. 1)then
          deallocate(var_buff)
          ialloc = 0
      endif

      write(6,*)' Normal finish of barnes_multivariate.f'

      return
      end



      subroutine barnes_multivariate_sub &
                           (var                             &! Output
                           ,aerr                            &! Output
                           ,n_var,max_obs,obs_barnes        &! Input
                           ,imax,jmax,kmax,grid_spacing_m   &! Inputs
                           ,fnorm_dum,n_fnorm_dum           &! Inputs
                           ,iter,i4time_sys                 &! Input
                           ,weight_bkg_const                &! Input
                           ,rtol,r_missing_data             &! Input
                           ,r0_barnes_max_m,r0_vert_grid    &! Input
                           ,ncnt_total,weight_total         &! Input
                           ,time_wt_obs                     &! Input
                           ,topo,ldf,ni_stat,nj_stat        &! Input
                           ,istatus)                        ! Outputs

!     Aug 1995 Steve Albers - This version handles multiple variables
!                             Used within wind, temp, and sfc analyses

      !$ use omp_lib
      implicit none

!     ....................Declare I/O variables...............................

      integer*4 n_var,max_obs                                         ! Input

      include 'barnesob.inc'
      type (barnesob) :: obs_barnes(max_obs)

      integer*4 imax,jmax,kmax                                        ! Input

      real*4    var(imax,jmax,kmax,n_var)                             ! Output

      real*4    aerr(imax,jmax,kmax,n_var)                            ! Output

      real*4    grid_spacing_m                                        ! Input
      integer*4 n_fnorm_dum                                           ! Input
      real*4    fnorm_dum                                             ! Input

!     Weight for Model Background. Recommended values: 0. to 1e+30.
!     This will make the output values match the background if far from obs.
!     A value of zero means this parameter is not active.
      real*4    weight_bkg_const                                      ! Input

!     This static data is used only in the case of the sfc analysis
      real*4 topo(ni_stat,nj_stat), ldf(ni_stat,nj_stat)              ! Input
      integer*4 ni_stat, nj_stat                                      ! Input

      integer*4 istatus                                               ! Output

!     Other input parameters
      integer*4 iter, i4time_sys, ncnt_total
      real*4 rtol, r_missing_data, r0_barnes_max_m, r0_vert_grid
      real*4 weight_total
      real*4 time_wt_obs(max_obs)

!     ....................Declare Local variables.............................
      
!      integer*4 max_var
!      parameter (max_var = 10)
      integer*4 l,i,ii,j,jj,k,kk,n,i_subscript,idx_obs
      integer*4 jblock,jblock_end,jblock_size
      integer*4 ilow_obs(max_obs),ihigh_obs(max_obs)
      integer*4 jlow_obs(max_obs),jhigh_obs(max_obs)
      integer*4 klow_obs(max_obs),khigh_obs(max_obs)
      integer*4 n_level_entries,level_alloc_status
      integer*4, allocatable :: level_obs_count(:)
      integer*4, allocatable :: level_obs_offset(:)
      integer*4, allocatable :: level_obs_next(:)
      integer*4, allocatable :: level_obs_index(:)
      real*4 r0_norm_sq,r0_value,ratio_norm_sq
      real*4 sum_var(imax,jmax,kmax,max_var)
      real*4 sumwt(imax,jmax,kmax),weight
      real*4 fnorm_max
      real*4 r0_barnes_max,r0_calc_min

!     These have a kmax dimension at least temporarily
      integer*4 n_cross_in

      real*4    wt_lut(-(imax-1):(imax-1),-(jmax-1):(jmax-1))
      real*4    fnorm_lut(-(imax-1):(imax-1),-(jmax-1):(jmax-1))

      real*4 r0_norm
      real*4 r0_value_min

      ! Function declarations
      real*4 fnorm_calc

      ! Local variables for OpenMP
      real*4 expm80, fnorm_0, time_wt
      real*4 wt_bkg_rel, wt_ob_dist, rdelt_roi, rdelt_m
      real*4 exponent, vertical_weight, weight_term
      real*4 weight_landfrac, diffl, const
      real*4 relax
      integer*4 idelt, jdelt, kdelt
      integer*4 ilow, ihigh, jlow, jhigh, klow, khigh
      
      ! OpenMP timing
      real*8 t1, t2

!     ...................Start Executable Statements..........................

      istatus = 0

      write(6,1234)iter
 1234 format(1x,'barnes_multivariate:',' iter=',i3)

      call get_fnorm_max(imax,jmax,r0_norm,r0_value_min,fnorm_max)
      expm80 = exp(-80.)

      r0_norm_sq = r0_norm**2

!     Maximum radius of influence in grid points (for no data coverage)
      r0_barnes_max = r0_barnes_max_m / grid_spacing_m

!     Check for possibility of illegal value in fnorm LUT
      write(6,*)'r0_value_min,fnorm_max,n_fnorm_dum', &
                r0_value_min,fnorm_max,n_fnorm_dum

      write(6,*)'r0_barnes_max,r0_barnes_max_m', &
                r0_barnes_max,r0_barnes_max_m
      write(6,*)'r0_vert_grid',r0_vert_grid

      fnorm_0 = fnorm_calc(0,r0_norm_sq,expm80)

      write(6,*)'weight_bkg_const,fnorm_0,ratio', &
                weight_bkg_const,fnorm_0,weight_bkg_const/fnorm_0

!     Create a lookup table for wt_lut
      !$OMP PARALLEL DO PRIVATE(i,j,ratio_norm_sq,i_subscript) COLLAPSE(2)
      do i = -(imax-1),(imax-1)
      do j = -(jmax-1),(jmax-1)
          wt_lut(i,j) = i*i+j*j
          if(.true.)then      ! l_3d
!             Nominal radius_sq of influence divided by 
!             desired radius_sq of influence
              ratio_norm_sq = r0_norm_sq / r0_barnes_max**2
              i_subscript = 0.5 + (wt_lut(i,j)*ratio_norm_sq)

!             Horizontal Weight
              fnorm_lut(i,j) = fnorm_calc(i_subscript,r0_norm_sq,expm80)
          endif         
      enddo
      enddo
      !$OMP END PARALLEL DO
      
!     Initialize arrays with OpenMP
      !$OMP PARALLEL DO PRIVATE(i,j,k,l) COLLAPSE(3)
      do k = 1, kmax
      do j = 1, jmax
      do i = 1, imax
          do l = 1, max_var
              sum_var(i,j,k,l) = 0.0
          enddo
          sumwt(i,j,k) = 0.0
      enddo
      enddo
      enddo
      !$OMP END PARALLEL DO

      write(6,*)'ncnt_total',ncnt_total,'weight_total',weight_total

!     Calculate search radius for gridpoints around each ob based on
!     error tolerance. This will be extra cautious assuming lots of obs
!     associated with 3D weighting.

!     Weight of model background relative to observation at zero distance
      wt_bkg_rel = weight_bkg_const / fnorm_0
      write(6,*)'wt_bkg_rel',wt_bkg_rel

!     Distance weight allowed for individual observations outside the radius
!     of influence that are omitted.
      wt_ob_dist = wt_bkg_rel * (rtol / max(weight_total,1.0)  )

      rdelt_roi = sqrt(-log(wt_ob_dist))
      rdelt_m = r0_barnes_max_m * rdelt_roi
      idelt = nint(rdelt_m / grid_spacing_m)
      jdelt = idelt
      kdelt = int(rdelt_roi * r0_vert_grid) + 1

      write(6,*)'     rtol     wt_ob   grid_spac rdelt_roi  rdelt_m  ', &
               ' idelt  kdelt'
      write(6,405)rtol,wt_ob_dist,grid_spacing_m,rdelt_roi,rdelt_m,idelt, &
                 kdelt
 405  format(1x,2e11.3,f10.0,f8.3,f10.0,i8,i5)

      write(6,*)' Summing weights...'
      write(6,*)'   n    i    j    k   kk  vert_wt  time_wt  value'
      
!     Print first 20 observations for debugging (before parallel region)
      do n=1,min(20,ncnt_total)
          i = obs_barnes(n)%i
          j = obs_barnes(n)%j
          k = obs_barnes(n)%k
          time_wt = time_wt_obs(n)
          
          ! Show only the diagonal element (kk=k)
          exponent = -( 0.0/r0_vert_grid )**2
          vertical_weight = exp(exponent)
          write(6,501)n,i,j,k,k,vertical_weight,time_wt, &
                     obs_barnes(n)%value(1)       
 501      format(5i5,2f8.4,f8.2)
      enddo
      
      !$ t1 = omp_get_wtime()

!     Sum the weights.  For 3-D analyses each (level, y-block) is owned by one
!     thread, so the large sum arrays no longer need an OpenMP array reduction.
!     Each grid point still receives observations in ascending input order.
      if(kmax .gt. 1)then ! 3D field analysis

          !$OMP PARALLEL DO PRIVATE(i,j,k)
          do n=1,ncnt_total
              i = obs_barnes(n)%i
              j = obs_barnes(n)%j
              k = obs_barnes(n)%k
              ilow_obs(n)  = max(i-idelt,1)
              ihigh_obs(n) = min(i+idelt,imax)
              jlow_obs(n)  = max(j-jdelt,1)
              jhigh_obs(n) = min(j+jdelt,jmax)
              klow_obs(n)  = max(k-kdelt,1)
              khigh_obs(n) = min(k+kdelt,kmax)
          enddo
          !$OMP END PARALLEL DO

!         Build a stable per-level observation index.  Entries are appended
!         while walking observations in their original order, so replacing the
!         full observation scan below does not change any gridpoint sum order.
          allocate(level_obs_count(kmax),level_obs_offset(kmax+1) &
                  ,level_obs_next(kmax),STAT=level_alloc_status)
          if(level_alloc_status .ne. 0)then
              write(6,*)' ERROR: Could not allocate Barnes level index'
              stop
          endif

          level_obs_count = 0
          do n=1,ncnt_total
              do kk=klow_obs(n),khigh_obs(n)
                  level_obs_count(kk) = level_obs_count(kk) + 1
              enddo
          enddo

          level_obs_offset(1) = 1
          do kk=1,kmax
              level_obs_offset(kk+1) = level_obs_offset(kk) &
                                     + level_obs_count(kk)
              level_obs_next(kk) = level_obs_offset(kk)
          enddo

          n_level_entries = level_obs_offset(kmax+1) - 1
          allocate(level_obs_index(max(n_level_entries,1)) &
                  ,STAT=level_alloc_status)
          if(level_alloc_status .ne. 0)then
              write(6,*)' ERROR: Could not allocate Barnes level entries'
              stop
          endif

          do n=1,ncnt_total
              do kk=klow_obs(n),khigh_obs(n)
                  level_obs_index(level_obs_next(kk)) = n
                  level_obs_next(kk) = level_obs_next(kk) + 1
              enddo
          enddo

          jblock_size = 8
          !$OMP PARALLEL DO COLLAPSE(2) SCHEDULE(DYNAMIC,1) &
          !$OMP PRIVATE(idx_obs,n,i,j,k,ilow,ihigh,jlow,jhigh,jblock_end) &
          !$OMP PRIVATE(time_wt,exponent,vertical_weight,weight_term) &
          !$OMP PRIVATE(jj,ii,weight,l)
          do kk=1,kmax
          do jblock=1,jmax,jblock_size
              jblock_end = min(jblock+jblock_size-1,jmax)
              do idx_obs=level_obs_offset(kk),level_obs_offset(kk+1)-1
                  n = level_obs_index(idx_obs)

                  jlow  = max(jlow_obs(n),jblock)
                  jhigh = min(jhigh_obs(n),jblock_end)
                  if(jlow .gt. jhigh) cycle

                  i = obs_barnes(n)%i
                  j = obs_barnes(n)%j
                  k = obs_barnes(n)%k
                  ilow  = ilow_obs(n)
                  ihigh = ihigh_obs(n)
                  time_wt = time_wt_obs(n)

                  exponent = -( float(kk-k)/r0_vert_grid )**2
                  vertical_weight = exp(exponent)

                  weight_term = obs_barnes(n)%weight * vertical_weight &
                                                     * time_wt      

                  do jj=jlow,jhigh
                  do ii=ilow,ihigh
                      weight = fnorm_lut(ii-i,jj-j) * weight_term
                      do l = 1,n_var
                          sum_var(ii,jj,kk,l) = sum_var(ii,jj,kk,l) &
                                       + (weight*obs_barnes(n)%value(l))       
                      enddo ! l
                      sumwt(ii,jj,kk) = sumwt(ii,jj,kk) + weight
                  enddo ! ii
                  enddo ! jj
              enddo ! n
          enddo ! jblock
          enddo ! kk
          !$OMP END PARALLEL DO

          deallocate(level_obs_index,level_obs_next &
                    ,level_obs_offset,level_obs_count)

      else ! sfc analysis - add in landfrac weight

          if(n_var .gt. 1)then
              stop
          endif

          ! For surface analysis, use similar reduction approach
          !$OMP PARALLEL DO REDUCTION(+:sum_var,sumwt) &
          !$OMP PRIVATE(i,j,k,ilow,ihigh,jlow,jhigh,klow,khigh) &
          !$OMP PRIVATE(time_wt,kk,exponent,vertical_weight,weight_term) &
          !$OMP PRIVATE(jj,ii,weight,weight_landfrac,const,diffl)
          do n=1,ncnt_total
              i = obs_barnes(n)%i
              j = obs_barnes(n)%j
              k = obs_barnes(n)%k

              ilow  = max(i-idelt,1)
              ihigh = min(i+idelt,imax)
              jlow  = max(j-jdelt,1)
              jhigh = min(j+jdelt,jmax)
              klow  = max(k-kdelt,1)
              khigh = min(k+kdelt,kmax)

              time_wt = time_wt_obs(n)

              do kk=klow,khigh
                  exponent = -( float(kk-k)/r0_vert_grid )**2
                  vertical_weight = exp(exponent)

                  weight_term = obs_barnes(n)%weight * vertical_weight &
                                                     * time_wt      

                  do jj=jlow,jhigh
                  do ii=ilow,ihigh

                      if (obs_barnes(n)%mask_sea .ne. 1) then
                          weight_landfrac = 1 ! No landfrac weighting

                      elseif(.true.)then ! threshold method

                          if (obs_barnes(n)%ldf .gt. 0) then
                              if (ldf(ii,jj) .lt. 0.01) then
                                  weight_landfrac = 0.
                              else
                                  weight_landfrac = 1.
                              endif
                          else
                              if (ldf(ii,jj) .lt. 0.01) then
                                  weight_landfrac = 1.
                              else
                                  weight_landfrac = 0.
                              endif
                          endif
                          
                      elseif(.false.)then ! hybrid method
                          const = 0.05
                          diffl = ABS(obs_barnes(n)%ldf - ldf(ii,jj))
                          IF (((obs_barnes(n)%ldf .GT. 0.) .AND. &
                                      (ldf(ii,jj) .EQ. 0.)) .OR. &
                              ((obs_barnes(n)%ldf .EQ. 0.) .AND. &
                                      (ldf(ii,jj) .GT. 0.))) THEN
                              weight_landfrac = EXP((-diffl/const)**2)
                          ELSE
                              weight_landfrac = 1
                          ENDIF

                      elseif(.false.)then ! exponential method
                          continue
                      endif

                      weight = fnorm_lut(ii-i,jj-j) * weight_term &
                                                    * weight_landfrac

                      sum_var(ii,jj,1,1) = sum_var(ii,jj,1,1) &
                                       + (weight*obs_barnes(n)%value(1))     
                      sumwt(ii,jj,1) = sumwt(ii,jj,1) + weight

                  enddo ! ii
                  enddo ! jj

              enddo ! kk
          enddo ! n
          !$OMP END PARALLEL DO

      endif ! 3D or sfc analysis

      !$ t2 = omp_get_wtime()
      !$ if(.true.) write(6,*) 'Weight accumulation time (sec):', t2-t1

      relax = 1.0 ! allows for SUR or SOR with each iteration

!     Divide the weights - Simple parallel loop
      !$ t1 = omp_get_wtime()
      
      !$OMP PARALLEL DO PRIVATE(l) COLLAPSE(3)
      do k=1,kmax
      do j=1,jmax
      do i=1,imax
              if(sumwt(i,j,k) + weight_bkg_const .eq. 0.)then
                  do l = 1,n_var
                      var(i,j,k,l) = r_missing_data
                  enddo ! l
              else
                  do l = 1,n_var
                      var(i,j,k,l)=sum_var(i,j,k,l) * relax &
                                / (sumwt(i,j,k) + weight_bkg_const)
                  enddo ! l
              endif

      enddo ! i
      enddo ! j
      enddo ! k
      !$OMP END PARALLEL DO

      !$ t2 = omp_get_wtime()
      !$ if(.true.) write(6,*) 'Weight division time (sec):', t2-t1

      istatus = 1

      return
      end


      subroutine get_fnorm_max(imax,jmax                         &! I
                              ,r0_norm,r0_value_min,fnorm_max)   ! O

      implicit none
      integer*4 imax, jmax                      ! Input
      real*4 r0_norm                            ! Output

!     Minimum radius of influence in grid points (for solid data coverage)
      real*4 r0_value_min                       ! Output
      real*4 fnorm_max                          ! Output

      character*8 c8_project
      integer*4 istatus
      real*4 r0_norm_sq, ratio_fnorm_sq

      call get_c8_project(c8_project,istatus)

      if(c8_project .eq. 'CWB')then
          r0_norm = 30.                         ! Grid point lengths
      else
          r0_norm = 10.                         ! Grid point lengths
      endif

      r0_value_min = 1.7

      r0_norm_sq = r0_norm**2
      ratio_fnorm_sq = r0_norm_sq / (r0_value_min**2)
      fnorm_max = (float(imax-1)**2 + float(jmax-1)**2) * ratio_fnorm_sq

      return
      end


      subroutine get_rms_barnesobs(u,ni,nj,nk,r_missing_data,nobs      &! I/O 
                            ,n_var,i_var,max_obs,obs_barnes,ncnt_total &! I
                            ,rms_obs,rmsu)                             ! O

      implicit none
      
      include 'barnesob.inc'
      type (barnesob) :: obs_barnes(max_obs)

      integer*4 ni,nj,nk,n_var,i_var,max_obs,ncnt_total
      real*4 u(ni,nj,nk)
      integer*4 nobs
      real*4 r_missing_data, rms_obs, rmsu
      real*4 residualu, sumsq_obs
      
      integer*4 n,i,j,k,nprint
      real*4 ob, diffu

      nobs = 0
      residualu = 0.
      sumsq_obs = 0.

      write(6,*)' get_rms_barnesobs...'
      write(6,*)'   n    i    j    k          uo         u      diffu'

      if(nk .gt. 1)then
          nprint = 20
      else
          nprint = 100
      endif
      do n = 1,ncnt_total

          i = obs_barnes(n)%i
          j = obs_barnes(n)%j
          k = obs_barnes(n)%k

          ob = obs_barnes(n)%value(i_var)

          if(ob        .ne. r_missing_data .and. &
              u(i,j,k) .ne. r_missing_data      )then
              nobs = nobs + 1
              diffu = ob - u(i,j,k)
              residualu = residualu + diffu ** 2
              sumsq_obs = sumsq_obs + ob ** 2

              if(nobs .le. nprint)then
                  write(6,1)nobs,i,j,k,ob,u(i,j,k),diffu
 1                format(4i5,2f12.3,f10.3)
              endif ! nobs
          endif ! Valid Data

      enddo ! n
      if(nobs .gt. 0)then
          rmsu =    sqrt(residualu/float(nobs))
          rms_obs = sqrt(sumsq_obs/float(nobs))
      else
          rmsu = 0.
          rms_obs = 0.
      endif

      return

      end

      
      function fnorm_calc(iii,r0_norm_sq,expm80)

      implicit none
      integer*4 iii
      real*4 r0_norm_sq, expm80, fnorm_calc
      real*4 exp_offset
      real*4 dist_norm_sq, arg

!     When the distance = r0_norm, the fnorm is effectively 1
!     call get_fnorm_max(imax,jmax                                    ! I
!    1                  ,r0_norm,r0_value_min_dum,fnorm_max_dum)      ! O

!     r0_norm_sq = r0_norm**2

      parameter (exp_offset = 70.)

      dist_norm_sq = (float(iii)/r0_norm_sq)
      arg = dist_norm_sq - exp_offset
      if(arg .le. 80.)then
          fnorm_calc = exp(-arg)
      else
          fnorm_calc = expm80
      endif

      return
      end


      subroutine arrays_to_barnesobs(imax,jmax,kmax                   &! I
                                    ,r_missing_data                   &! I
                                    ,varo,weight_3d                   &! I
                                    ,n_var,max_obs,obs_barnes         &! I/O
                                    ,ncnt_total,weight_total          &! O
                                    ,istatus)                         ! O

!     Map obs from the 3-D arrays into the 'obs_barnes' data structure

      implicit none
      
      include 'barnesob.inc'
      type (barnesob) :: obs_barnes(max_obs)

      integer*4 imax,jmax,kmax,n_var,max_obs
      real*4    varo(imax,jmax,kmax,n_var),weight_3d(imax,jmax,kmax)  
      real*4    r_missing_data
      integer*4 ncnt_total, istatus
      real*4    weight_total
      
      integer*4 i,j,k,l

      ncnt_total=0
      weight_total = 0.

!     Count obs and map obs into data structure
      do k=1,kmax
      do j=1,jmax
      do i=1,imax
          if(varo(i,j,k,1) .ne. r_missing_data)then

              if(ncnt_total .ge. max_obs)then
                  write(6,*)' ERROR: Too many obs for barnes', &
                           ncnt_total,max_obs
                  istatus = 0
                  return
              else

!                 Increment ob counter
                  ncnt_total = ncnt_total + 1
                  weight_total = weight_total + weight_3d(i,j,k)

                  obs_barnes(ncnt_total)%i      = i
                  obs_barnes(ncnt_total)%j      = j
                  obs_barnes(ncnt_total)%k      = k
                  obs_barnes(ncnt_total)%weight = weight_3d(i,j,k)       
                  do l = 1,n_var
                      obs_barnes(ncnt_total)%value(l) = varo(i,j,k,l)
                  enddo ! l

              endif ! Not too many obs

          endif ! We have an ob

      enddo ! i
      enddo ! j
      enddo ! k

      istatus = 1
      return
      end


      subroutine get_time_wt(i4time_sys,i4time_ob,time_wt,istatus)

      implicit none
      integer*4 i4time_sys, i4time_ob, istatus
      real*4 time_wt, arg

      arg = float(i4time_sys-i4time_ob) / 3600.

      if(abs(arg) .gt. 10.)then
          !$OMP CRITICAL (barnes_time_diagnostic)
          write(6,*)' Error, check times in get_time_wt'
          !$OMP END CRITICAL (barnes_time_diagnostic)
          time_wt = 1.0
          istatus = 0
          return

      else
          time_wt = exp(-(arg**2))

      endif

!     time_wt = 1.0 ! test 

      istatus = 1
      return
      end
