cdis   
cdis    Open Source License/Disclaimer, Forecast Systems Laboratory
cdis    NOAA/OAR/FSL, 325 Broadway Boulder, CO 80305
cdis    
cdis    This software is distributed under the Open Source Definition,
cdis    which may be found at http://www.opensource.org/osd.html.
cdis    
cdis    In particular, redistribution and use in source and binary forms,
cdis    with or without modification, are permitted provided that the
cdis    following conditions are met:
cdis    
cdis    - Redistributions of source code must retain this notice, this
cdis    list of conditions and the following disclaimer.
cdis    
cdis    - Redistributions in binary form must provide access to this
cdis    notice, this list of conditions and the following disclaimer, and
cdis    the underlying source code.
cdis    
cdis    - All modifications to this software must be clearly documented,
cdis    and are solely the responsibility of the agent making the
cdis    modifications.
cdis    
cdis    - If significant modifications or enhancements are made to this
cdis    software, the FSL Software Policy Manager
cdis    (softwaremgr@fsl.noaa.gov) should be notified.
cdis    
cdis    THIS SOFTWARE AND ITS DOCUMENTATION ARE IN THE PUBLIC DOMAIN
cdis    AND ARE FURNISHED "AS IS."  THE AUTHORS, THE UNITED STATES
cdis    GOVERNMENT, ITS INSTRUMENTALITIES, OFFICERS, EMPLOYEES, AND
cdis    AGENTS MAKE NO WARRANTY, EXPRESS OR IMPLIED, AS TO THE USEFULNESS
cdis    OF THE SOFTWARE AND DOCUMENTATION FOR ANY PURPOSE.  THEY ASSUME
cdis    NO RESPONSIBILITY (1) FOR THE USE OF THE SOFTWARE AND
cdis    DOCUMENTATION; OR (2) TO PROVIDE TECHNICAL SUPPORT TO USERS.
cdis   
cdis
cdis
cdis   
cdis

cdis    Cloud-BAL: failure status initialization and nonzero error exits.
cdis    Wind analysis calculations and writer arguments are unchanged.


        subroutine lapswind_anal  (i4time_lapswind,NX_L,NY_L,NZ_L,
     1              NTMIN,NTMAX,
     1              max_radars,N_MESO,N_SAO,N_PIREP,
     1              r_missing_data,i2_missing_data,
     1              n_prods_out,
     1              i4time_array,
     1              j_status)

!       1990         Steve Albers  (Original Version)
!       1992 Apr 30  Steve Albers  (Mod for multi-radar Doppler velocities)
!       1993 Feb 20  Steve Albers  Subroutinize the profiler processing
!       1993 Apr     Steve Albers  Accept RAMS background
!       1993 Nov     Steve Albers  Partial OE interface, 1st guess subroutine
!                                  Eliminate arrays.f from other subroutines
!                                  Eliminate common blocks
!       1994 Oct     Steve Albers  Add i4time_radar_a array
!                                  Move Usfc, Vsfc from LW3 to LWM file
!       1994 Nov 01  Steve Albers  Pass additional arguments into laps_anl
!       1995 Aug     Steve Albers  Some of the U and V arrays are now
!                                  equivalenced to make passing them around
!                                  into a generic Barnes routine easier.
!       1995 Nov     K. Brewster   Changes for nyquist velocity array
!                                  and sounding profiles
!       1995 Nov 28  Steve Albers  iradar_cycle_time = 600 (from 60)
!       1995 Dec  8  Steve Albers  Calls to separate ref and vel radar access
!                                  routines (in getradar.f)
!       1996 Aug     Steve Albers  Mods to allow option to rotate to grid
!                                  north.
!       1997 Feb     Steve Albers  Cleaned up some unneeded arrays/variables
!       1997 Mar     Steve Albers  Removed equiv statements.
!       1997 Jun     Ken Dritz     Removed NZ_L_MAX from the argument list
!                                  in the call to get_fg_wind (it is not
!                                  actually used in get_fg_wind).
!       1997 Jun     Ken Dritz     Changed RETURN statement to STOP statement
!                                  in handling of istatus .ne. 1 after return
!                                  from call to get_domain_laps.
!       1997 Jun     Ken Dritz     Added r_missing_data as dummy argument.
!       1997 Jun     Ken Dritz     Removed parameter declaration of NPTS
!                                  as NX_L * NY_L (because it is unused).
!       1997 Jun     Ken Dritz     Removed parameter declaration of K_3D
!                                  as 2 * NZ_L (because it is unused).
!       1997 Jun     Ken Dritz     Pass N_PIREP in call to rdpirep.
!       1997 Jun     Ken Dritz     Pass NX_L and NY_L a second time to
!                                  vert_wind (once for dummy arguments ni,nj
!                                  and once for newly added dummy arguments
!                                  NX_L_MAX and NY_L_MAX).
!       1997 Jun     Ken Dritz     Pass r_missing_data to vert_wind.
!       1998 Feb     Steve Albers  Call rdpirep with cloud drift winds also

        integer*4 max_obs
        parameter (max_obs = 100000)       ! 60000 -> 100000 (changed by  WHY, 2026.06.22.)
        include 'barnesob.inc'
        type (barnesob) :: obs_point(max_obs)                           

        include 'windparms.inc'

!       LAPS Grid Dimensions

        real*4 lat(NX_L,NY_L)
        real*4 lon(NX_L,NY_L)
        real*4 topo(NX_L,NY_L)

        real*4 rk_terrain(NX_L,NY_L)

!       Laps Analysis Grids
        real grid_laps_wt(NX_L,NY_L,NZ_L)
        real grid_laps_u(NX_L,NY_L,NZ_L)
        real grid_laps_v(NX_L,NY_L,NZ_L)

        include 'main_sub.inc'

!       Housekeeping
        integer*4       ss_normal,rtsys_no_data
        parameter(ss_normal        =1, ! success
     1            rtsys_no_data    =3)


        integer*4 j_status(20),i4time_array(20)
        character*3 exts(20),ext_in

        real*4 rlat_radar(max_radars),rlon_radar(max_radars)
     1                               ,rheight_radar(max_radars)
        character*4 radar_name(max_radars)
        real*4 v_nyquist_in(max_radars)
        integer*4 n_vel_grids(max_radars),i4time_radar_a(max_radars)

        integer*4 thresh_2_radarobs_lvl_unfltrd
     1           ,thresh_4_radarobs_lvl_unfltrd

!       Stuff for call to LAPS analysis
!       real*4 upass1(NX_L,NY_L,NZ_L),vpass1(NX_L,NY_L,NZ_L)

        real*4 uanl(NX_L,NY_L,NZ_L),vanl(NX_L,NY_L,NZ_L) ! WRT True North

        dimension u_laps_fg(NX_L,NY_L,NZ_L),v_laps_fg(NX_L,NY_L,NZ_L)

!       dimension u_mdl_bkg_4d(NX_L,NY_L,NZ_L,NTMIN:NTMAX)
!       dimension v_mdl_bkg_4d(NX_L,NY_L,NZ_L,NTMIN:NTMAX)

        integer*4  N_3D_FIELDS
        parameter (N_3D_FIELDS = 3)

!       real*4 outarray_4D(NX_L,NY_L,NZ_L,N_3D_FIELDS)
        character*125 comment_3D(N_3D_FIELDS)
        character*10 units_3D(N_3D_FIELDS)
        character*3 var_3D(N_3D_FIELDS)

        character*125 comment_2d,comment_a(2)
        character*10 units_2d,units_a(2)
        character*3 var_2d,var_a(2)

        character*31 EXT
!       character*31 ext_fg

!       Stuff for SFC Winds
        real*4 uanl_sfcitrp(NX_L,NY_L),vanl_sfcitrp(NX_L,NY_L)
        real*4 out_sfc_3D(NX_L,NY_L,2)

        real*4 grid_ra_vel(NX_L,NY_L,NZ_L,MAX_RADARS)
        real*4 grid_ra_nyq(NX_L,NY_L,NZ_L,MAX_RADARS)
        integer*4 idx_radar_a(MAX_RADARS)
        character*31 ext_radar(MAX_RADARS)

        real*4 heights_3d(NX_L,NY_L,NZ_L)
        real*4 heights_1d(NZ_L)

        logical l_use_raob, l_use_cdw, l_use_radial_vel

!       Local for laps_anl
        integer*4 n_obs_lvl(NZ_L)

        integer*4 i4_loop_total
        save i4_loop_total
        data i4_loop_total/0/


! ****  Declarations for OE code **********************************************
        logical l_oe
        data l_oe /.false./

!       integer horizontal_winds        ! C subroutine

! ****  END Declarations for OE code *******************************************



csms$serial(<grid_spacing_m, weight_bkg_const, n_radars, 
csms$>       grid_ra_vel,grid_ra_nyq,idx_radar_a,    ! Not needed in || region?
csms$>       v_nyquist_in,istat_radar_vel,           ! Not needed in || region?
csms$>       n_vel_grids,                            ! Not needed in || region?
csms$>       rlat_radar,rlon_radar,rheight_radar,    ! Not needed in || region?
csms$>                                     out>:default=ignore)  begin

        j_status = 3
        i4time_array = 0
        n_prods_out = 0

        write(6,*)' Welcome to the LAPS Wind Analysis'

        call get_wind_parms(l_use_raob,l_use_cdw,l_use_radial_vel
     1                     ,thresh_2_radarobs_lvl_unfltrd
     1                     ,thresh_4_radarobs_lvl_unfltrd
     1                     ,weight_bkg_const
     1                     ,weight_radar
     1                     ,rms_thresh_wind
     1                     ,max_pr,max_pr_levels,i_3d
     1                     ,istatus)
        if(istatus .ne. 1)then
            write(6,*)' Error getting wind parms'
            stop 1
        endif

        i_3d = 1

        if(max_radars .eq. 0 .and. l_use_radial_vel)then
            write(6,*)' WARNING: max_radars = 0, '
     1               ,'setting l_use_radial_vel to .false.'
            l_use_radial_vel = .false.
        endif

!       Read lat/lon and topo data
        call read_static_grid(NX_L,NY_L,'LAT',lat,istatus)
        if(istatus .ne. 1)then
            write(6,*)' Error getting LAPS LAT'
            stop 1
        endif

        call read_static_grid(NX_L,NY_L,'LON',lon,istatus)
        if(istatus .ne. 1)then
            write(6,*)' Error getting LAPS LON'
            stop 1
        endif

        call read_static_grid(NX_L,NY_L,'AVG',topo,istatus)
        if(istatus .ne. 1)then
            write(6,*)' Error getting LAPS topo'
            stop 1
        endif

!       Get actual grid spacing valid at the gridpoint nearest the center
        icen = NX_L/2 + 1
        jcen = NY_L/2 + 1
        call get_grid_spacing_actual(lat(icen,jcen),lon(icen,jcen)
     1                              ,grid_spacing_m,istatus)
        if(istatus .ne. 1)then
            write(6,*)' Error return from get_grid_spacing_actual'       
            stop 1
        endif

!       write(15,*)' I4time of data = ',i4time_lapswind
10      continue

        ISTAT = INIT_TIMER()

        n_prods_out = 1 ! (Any number > 0)

!       Housekeeping
        n_prods = 7
        do i = 1,n_prods
            j_status(i) = rtsys_no_data
            i4time_array(i) = i4time_lapswind ! Default Value
        enddo ! i

        n_msg = 1
        n_pig = 2
        n_prg = 3
        n_sag = 4
        n_d00 = 5
        n_lw3 = 6
        n_lwm = 7

        exts(n_msg) = 'msg'
        exts(n_pig) = 'pig'
        exts(n_prg) = 'prg'
        exts(n_sag) = 'sag'
        exts(n_d00) = 'd00'
        exts(n_lw3) = 'lw3'
        exts(n_lwm) = 'lwm'

        EXT = 'lw3'

        write(6,*)' swlat ',lat(   1,   1)
        write(6,*)' nwlat ',lat(   1,NY_L)
        write(6,*)' selat ',lat(NX_L,   1)
        write(6,*)' nelat ',lat(NX_L,NY_L)

        write(6,*)' swlon ',lon(   1,   1)
        write(6,*)' nwlon ',lon(   1,NY_L)
        write(6,*)' selon ',lon(NX_L,   1)
        write(6,*)' nelon ',lon(NX_L,NY_L)

        istat_ht = 0

        if(.false.)then ! READ IN LAPS HEIGHTS
            write(6,*)
            write(6,*)' Getting 3_D Height Analysis from LAPS:'

            var_2d = 'HT'
            ext = 'lt1'

            call get_laps_3dgrid(i4time_lapswind,0,i4time_nearest
     1               ,NX_L,NY_L,NZ_L,ext,var_2d,units_2d,comment_2d
     1               ,heights_3d,istat_ht)

            if(istat_ht .ne. 1)then
                write(6,*)' Note, could not read 3D LAPS Heights'
     1                   ,' - looking for MODEL'
            endif

        endif ! .false.

        if(istat_ht .eq. 0)then ! Get 3d MODEL height grid
            write(6,*)
            write(6,*)' Getting 3_D Height Analysis from MODEL:'

            var_2d = 'HT'

            call get_modelfg_3d(i4time_lapswind,var_2d
     1                               ,NX_L,NY_L,NZ_L
     1                               ,heights_3d,istat_ht)

            if(istat_ht .ne. 1)then
                write(6,*)
     1    ' Aborting from LAPS Wind Anal - Error in getting MDL heights'
                return
            endif

        endif ! We need to look for MODEL

!       Initialize grids with the missing data value
        do k = 1,NZ_L
        do j = 1,NY_L
        do i = 1,NX_L
            grid_laps_u(i,j,k) = r_missing_data
            grid_laps_v(i,j,k) = r_missing_data
            grid_laps_wt(i,j,k) = r_missing_data
        enddo
        enddo
        enddo

        call get_laps_cycle_time(ilaps_cycle_time,istatus)
        if(istatus .eq. 1)then
            write(6,*)' ilaps_cycle_time = ',ilaps_cycle_time
        else
            write(6,*)' Error getting laps_cycle_time'
            return
        endif

!  ***  Remap Radial Velocities to LAPS Grid  *****************************
!       i4_tol = max(ilaps_cycle_time / 2, iradar_cycle_time / 2)
        i4_tol = 900 ! seconds

        if(l_use_radial_vel)then
            write(6,*)
            write(6,*)' Reading radial velocity data'
            call get_multiradar_vel(i4time_lapswind,i4_tol           ! I
     1       ,i4time_radar_a                                         ! O
     1       ,max_radars                                             ! I
     1       ,n_radars                                               ! O
     1       ,ext_radar                                              ! O
     1       ,r_missing_data,.true.,NX_L,NY_L,NZ_L                   ! I
     1       ,grid_ra_vel,grid_ra_nyq,idx_radar_a,v_nyquist_in       ! O
     1       ,n_vel_grids                                            ! O
     1       ,rlat_radar,rlon_radar,rheight_radar,radar_name         ! O
     1       ,istat_radar_vel,istat_radar_nyq)                       ! O

            if(n_radars .gt. 0)then
                write(6,*)
                write(6,5545)(radar_name(i),i=1,n_radars)
5545            format(' Retrieved radar Names:',30(1x,a4))
            endif

            if(istat_radar_vel .eq. 1)then
                write(6,*)' Radar 3d vel data successfully read in'
     1                      ,(n_vel_grids(i),i=1,n_radars)
            else
                write(6,*)' Radar 3d vel data NOT successfully read in'
     1                      ,(n_vel_grids(i),i=1,n_radars)
            endif

        else
            n_radars = 0
            istat_radar_vel = 0
            write(6,*)' Not using radar 3d vel, l_use_radial_vel = '
     1               ,l_use_radial_vel

        endif ! l_use_radial_vel

        write(6,*)

!  ***  Read in Wind Obs **************************************************
!                         ( This reads in just the profiler so far)
!       We might consider passing back an observation "vector" or data
!       structure from this routine.

        write(6,*)' Calling get_wind_3d_obs'

        nobs_point = 0

        call get_wind_3d_obs(
     1            NX_L,NY_L,NZ_L,                                 ! I
     1            r_missing_data,i2_missing_data,                 ! I
     1            i4time_lapswind,heights_3d,heights_1d,          ! I
     1            MAX_PR,MAX_PR_LEVELS,weight_prof,l_use_raob,    ! I
     1            l_use_cdw,                                      ! I
     1            N_SAO,N_PIREP,                                  ! I
     1            lat,lon,                                        ! I
     1            NTMIN,NTMAX,                                    ! I
     1            u_laps_fg,v_laps_fg,                            ! O
     1            grid_laps_u,grid_laps_v,grid_laps_wt,           ! O
     1            max_obs,obs_point,nobs_point,                   ! I/O
     1            rlat_radar(1),rlon_radar(1),rheight_radar(1),   ! I
     1            istat_radar_vel,n_vel_grids(1),                 ! I
     1            grid_ra_vel(1,1,1,1),                           ! I
     1            istatus_remap_pro,                              ! O
     1            istatus                )                        ! O

        if(istatus .ne. 1)then
            write(6,*)' Abort LAPS wind analysis'
            return
        endif

        if(istatus_remap_pro .ne. 1)then
            return
        else
            i4time_array(n_prg) = i4time_lapswind
            j_status(n_prg) = ss_normal
        endif

        n_meso_obs = 0

        I4_elapsed = ishow_timer()

        if((.not. l_grid_north_bkg) .and. l_grid_north_anal)then       
                write(6,*)' Rotating first guess to grid north'

                do k = 1, NZ_L
                do j = 1, NY_L
                do i = 1, NX_L
                    call uvtrue_to_uvgrid(
     1                           u_laps_fg(i,j,k),v_laps_fg(i,j,k)
     1                          ,u_grid   ,v_grid
     1                          ,lon(i,j)           )
                    u_laps_fg(i,j,k) = u_grid
                    v_laps_fg(i,j,k) = v_grid
                enddo
                enddo
                enddo

                I4_elapsed = ishow_timer()

        endif

        if(l_grid_north_anal)then       
                write(6,*)' Rotating obs arrays to grid north'

                do k = 1, NZ_L
                do j = 1, NY_L
                do i = 1, NX_L
                    if(     grid_laps_u(i,j,k) .ne. r_missing_data
     1                .and. grid_laps_v(i,j,k) .ne. r_missing_data )then
                        call uvtrue_to_uvgrid(
     1                           grid_laps_u(i,j,k),grid_laps_v(i,j,k)
     1                          ,u_grid   ,v_grid
     1                          ,lon(i,j)           )
                        grid_laps_u(i,j,k) = u_grid
                        grid_laps_v(i,j,k) = v_grid
                    endif
                enddo
                enddo
                enddo

                write(6,*)' Rotating obs structure to grid north'
                do iob = 1,nobs_point
                    i = obs_point(iob)%i
                    j = obs_point(iob)%j
                    call uvtrue_to_uvgrid(obs_point(iob)%valuef(1)
     1                                   ,obs_point(iob)%valuef(2)
     1                                   ,u_grid   ,v_grid
     1                                   ,lon(i,j)           )
                    obs_point(iob)%valuef(1) = u_grid
                    obs_point(iob)%valuef(2) = v_grid
                enddo ! iob

                I4_elapsed = ishow_timer()

        endif ! l_grid_north

!       call get_fnorm_max(NX_L,NY_L,r0_norm,r0_value_min,fnorm_max)
!       n_fnorm = int(fnorm_max) + 1
csms$serial end

        call laps_anl(grid_laps_u,grid_laps_v
     1       ,obs_point,max_obs,nobs_point                              ! I
     1       ,n_radars,istat_radar_vel                                  ! I
     1       ,grid_ra_vel,grid_ra_nyq,v_nyquist_in,idx_radar_a          ! I
!    1       ,upass1,vpass1                                             ! O
     1       ,n_var                                                     ! I
     1       ,uanl,vanl                                                 ! O
     1       ,grid_laps_wt,weight_bkg_const,rms_thresh_wind             ! I/L
     1       ,max_radars                                                ! I
     1       ,n_vel_grids,rlat_radar,rlon_radar,rheight_radar           ! I
     1       ,thresh_2_radarobs_lvl_unfltrd                             ! I
     1       ,thresh_4_radarobs_lvl_unfltrd                             ! I
     1       ,u_laps_fg,v_laps_fg                                       ! I/L
     1       ,NX_L,NY_L,NZ_L,lat,lon                                    ! I
     1       ,i4time_lapswind,grid_spacing_m                            ! I
     1       ,r_missing_data                                            ! I
     1       ,heights_3d                                                ! I
     1       ,i4_loop_total                                             ! O
     1       ,l_derived_output,l_grid_north_anal,l_3pass                ! I
     1       ,l_correct_unfolding                                       ! I
!    1       ,n_iter_wind
     1       ,weight_cdw,weight_sfc,weight_pirep,weight_prof            ! I
     1       ,weight_radar                                              ! I
     1       ,istatus)                                                  ! O

csms$serial(default=ignore)  begin              

        if(istatus .ne. 1)then
                write(6,*)' Error in Wind Analysis (laps_anl)'
                return
        endif

        if(l_grid_north .and. .not. l_grid_north_out)then

                I4_elapsed = ishow_timer()

                write(6,*)' Rotating analyzed wind back to true north'
                do k = 1, NZ_L
                do j = 1, NY_L
                do i = 1, NX_L
                        call uvgrid_to_uvtrue(
     1                           uanl(i,j,k),vanl(i,j,k)
     1                          ,u_true   ,v_true
     1                          ,lon(i,j)           )
                    uanl(i,j,k) = u_true
                    vanl(i,j,k) = v_true
                enddo
                enddo
                enddo

                I4_elapsed = ishow_timer()

        endif ! rotate back to true north

        write(6,*)'uanl(NX_L/2+1,NY_L/2+1,1) = '
     1            ,uanl(NX_L/2+1,NY_L/2+1,1)
        write(6,*)'vanl(NX_L/2+1,NY_L/2+1,1) = '
     1            ,vanl(NX_L/2+1,NY_L/2+1,1)

        i4time_array(n_d00) = i4time_lapswind
        j_status(n_d00) = ss_normal

        I4_elapsed = ishow_timer()

!  **** Generate Interpolated SFC analysis ****

        write(6,*)' Generating interpolated laps surface wind'

        i_sfc_bad = 0

        do j = 1,NY_L
        do i = 1,NX_L

!           Interpolate from three dimensional grid to terrain surface
            zlow = height_to_zcoord2(topo(i,j),heights_3d,NX_L,NY_L,NZ_L
     1                                                  ,i,j,istatus)
            if(istatus .ne. 1)then
                write(6,*)' lapswind_anal: error in height_to_zcoord2'
     1                   ,' in sfc wind interpolation',istatus
                write(6,*)i,j,zlow,topo(i,j),
     1                    (heights_3d(i,j,k),k=1,NZ_L)
                return
            endif

            rk_terrain(i,j) = zlow

            klow = max(zlow,1.)
            khigh = klow + 1
            fraclow = float(khigh) - zlow
            frachigh = 1.0 - fraclow

            if( uanl(i,j,klow)  .eq. r_missing_data
     1     .or. vanl(i,j,klow)  .eq. r_missing_data
     1     .or. uanl(i,j,khigh) .eq. r_missing_data
     1     .or. vanl(i,j,khigh) .eq. r_missing_data        )then

                write(6,3333)i,j
3333            format(' Warning: cannot interpolate to sfc at ',2i3)
                i_sfc_bad = 1
                uanl_sfcitrp(i,j) = r_missing_data
                vanl_sfcitrp(i,j) = r_missing_data

            else
                uanl_sfcitrp(i,j) = uanl(i,j,klow ) * fraclow
     1                            + uanl(i,j,khigh) * frachigh

                vanl_sfcitrp(i,j) = vanl(i,j,klow ) * fraclow
     1                            + vanl(i,j,khigh) * frachigh

            endif

        enddo ! j
        enddo ! i

        I4_elapsed = ishow_timer()

        call wind_post_process(i4time_lapswind,EXT,var_3d
     1                        ,units_3d,comment_3d
     1                        ,uanl,vanl                            ! I
     1                        ,NX_L,NY_L,NZ_L,N_3D_FIELDS           ! I
     1                        ,uanl_sfcitrp,vanl_sfcitrp            ! I
     1                        ,topo,lat,lon,grid_spacing_m          ! I
     1                        ,rk_terrain                           ! I
     1                        ,r_missing_data,l_grid_north_out      ! I
     1                        ,istat_lw3)

!       Set notification arrays.f the wind analysis product
        if(istat_lw3 .eq. 1)then
            i4time_array(n_lw3) = i4time_lapswind
            j_status(n_lw3) = ss_normal
        else
            write(6,*)' Error writing out LW3 field'
        endif

        I4_elapsed = ishow_timer()

!       Write out derived winds file (sfc wind)
        ext = 'lwm'

        var_a(1) = 'SU'
        var_a(2) = 'SV'

        do i = 1,2
            units_a(i) = 'm/s'
            comment_a(i) = 'SFCWIND'
        enddo

        call move(uanl_sfcitrp,out_sfc_3D(1,1,1),NX_L,NY_L)
        call move(vanl_sfcitrp,out_sfc_3D(1,1,2),NX_L,NY_L)

        call put_laps_multi_2d(i4time_lapswind,ext,var_a
     1      ,units_a,comment_a,out_sfc_3d,NX_L,NY_L,2,istat_lwm)

        if(istat_lwm .eq. 1)then
            i4time_array(n_lwm) = i4time_lapswind
            j_status(n_lwm) = ss_normal
        else
            write(6,*)' Error writing out lwm file (SU,SV)'
        endif

        I4_elapsed = ishow_timer()

        write(6,*)' Status of output products'
        do i = 1,n_prods
            write(6,*)i,' ',exts(i),' '
     1                             ,i4time_array(i),j_status(i)
        enddo ! i

        if(i4_elapsed .gt. 0)then
            pct_loop_total = 
     1          float(i4_loop_total)/float(i4_elapsed) * 100.
        else
            pct_loop_total = 0.
        endif
        write(6,*)'i4time (FINAL) loop/elapsed/% ='
     1                                           ,i4_loop_total
     1                                           ,i4_elapsed     
     1                                           ,pct_loop_total

        write(6,*)' End of LAPS Wind Analysis'

csms$serial end

        return

        end


        subroutine wind_post_process(i4time_lapswind,EXT,var_3d
     1                              ,units_3d,comment_3d
     1                              ,uanl,vanl                            ! I
     1                              ,NX_L,NY_L,NZ_L                       ! I
     1                              ,N_3D_FIELDS                          ! I
     1                              ,uanl_sfcitrp,vanl_sfcitrp            ! I
     1                              ,topo,lat,lon,grid_spacing_m          ! I
     1                              ,rk_terrain                           ! I
     1                              ,r_missing_data,l_grid_north_out      ! I
     1                              ,istat_lw3)

        real*4 uanl(NX_L,NY_L,NZ_L),vanl(NX_L,NY_L,NZ_L) ! WRT True North ! I
        real*4 wanl(NX_L,NY_L,NZ_L)                                       ! L
        real*4 uanl_sfcitrp(NX_L,NY_L),vanl_sfcitrp(NX_L,NY_L)            ! I

        real*4 lat(NX_L,NY_L)
        real*4 lon(NX_L,NY_L)
        real*4 topo(NX_L,NY_L)

        real*4 rk_terrain(NX_L,NY_L)

        character*125 comment_3D(N_3D_FIELDS)
        character*10 units_3D(N_3D_FIELDS)
        character*3 var_3D(N_3D_FIELDS)
        character*3 EXT

        logical l_grid_north_out

csms$ignore begin
        istat_lw3 = 0
        write(6,*)' Subroutine wind_post_process...'

        write(6,*)' Computing Omega'
        call vert_wind(uanl,vanl,uanl_sfcitrp,vanl_sfcitrp                ! I
     1                ,NX_L,NY_L,NZ_L                                     ! I
     1                ,wanl                                               ! O
     1                ,topo,lat,lon,grid_spacing_m                        ! I
     1                ,rk_terrain,r_missing_data,l_grid_north_out         ! I
     1                ,istatus)                                           ! O

        if(istatus .ne. 1)then
            write(6,*)' Error: bad data detected by vert_wind'
            write(6,*)
     1      ' Check for missing data on one or more levels of uanl/vanl'
            return
        endif

        I4_elapsed = ishow_timer()


!       Header information for 3D wind
        EXT = 'lw3'

        units_3D(1) = 'M/S'
        units_3D(2) = 'M/S'
        units_3D(3) = 'PA/S'

        var_3D(1) = 'U3'
        var_3D(2) = 'V3'
        var_3D(3) = 'OM'

        comment_3D(1) = '3DWIND'
        comment_3D(2) = '3DWIND'
        comment_3D(3) = '3DWIND'

        I4_elapsed = ishow_timer()

        write(6,*)' Calling write routine for all grids ',ext(1:3)
     1                                  ,i4time_lapswind

!       call move_3d(uanl,outarray_4D(1,1,1,1),NX_L,NY_L,NZ_L)
!       call move_3d(vanl,outarray_4D(1,1,1,2),NX_L,NY_L,NZ_L)
!       call move_3d(wanl,outarray_4D(1,1,1,3),NX_L,NY_L,NZ_L)

!       call put_laps_multi_3d(i4time_lapswind,EXT,var_3d,units_3d,
!    1     comment_3d,outarray_4D,NX_L,NY_L,NZ_L,N_3D_FIELDS,istat_lw3)

        call put_laps_multi_3d_jacket(i4time_lapswind,EXT,var_3d
     1                               ,units_3d,comment_3d
     1                               ,uanl,vanl,wanl
     1                               ,NX_L,NY_L,NZ_L,N_3D_FIELDS
     1                               ,istat_lw3)

csms$ignore end
        return
        end


        subroutine put_laps_multi_3d_jacket(i4time_lapswind,EXT,var_3d
     1                                     ,units_3d,comment_3d
     1                                     ,uanl,vanl,wanl
     1                                     ,NX_L,NY_L,NZ_L
     1                                     ,N_3D_FIELDS,istat_lw3)

        real*4 uanl(NX_L,NY_L,NZ_L),vanl(NX_L,NY_L,NZ_L) ! WRT True North
        real*4 wanl(NX_L,NY_L,NZ_L)

        real*4 outarray_4D(NX_L,NY_L,NZ_L,N_3D_FIELDS)
        character*125 comment_3D(N_3D_FIELDS)
        character*10 units_3D(N_3D_FIELDS)
        character*3 var_3D(N_3D_FIELDS)
        character*3 EXT

csms$ignore begin
        istat_lw3 = 0
        write(6,*)' Subroutine put_laps_multi_3d_jacket...'

        call move_3d(uanl,outarray_4D(1,1,1,1),NX_L,NY_L,NZ_L)
        call move_3d(vanl,outarray_4D(1,1,1,2),NX_L,NY_L,NZ_L)
        call move_3d(wanl,outarray_4D(1,1,1,3),NX_L,NY_L,NZ_L)

        call put_laps_multi_3d(i4time_lapswind,EXT,var_3d,units_3d,
     1     comment_3d,outarray_4D,NX_L,NY_L,NZ_L,N_3D_FIELDS,istat_lw3)

csms$ignore end
        return
        end
