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

cdis    Cloud-BAL status overlay: producer validation and exit checks only.
cdis    Wind analysis calculations and writer logic are unchanged.

        program laps_wind

!       General declarations
        integer*4 j_status(20),i4time_array(20)
        character*9 a9_time
        logical log_open
        integer ios,log_len

        character*200 fname
	integer NX_L
	integer NY_L
	integer NZ_L

        j_status = 3
        i4time_array = 0
        n_prods = 0
        log_open = .false.
        log_len = 0
        fname = ' '

csms$serial begin
        call get_grid_dim_xy(NX_L,NY_L,istatus)
        if (istatus .ne. 1) then
           write (6,*) 'Error getting horizontal domain dimensions'
           go to 999
        endif

        call get_laps_dimensions(NZ_L,istatus)
        if (istatus .ne. 1) then
           write (6,*) 'Error getting vertical domain dimension'
           go to 999
        endif

        if (NX_L .le. 0 .or. NY_L .le. 0 .or. NZ_L .le. 0) then
           write (6,*) 'Invalid wind analysis dimensions'
           go to 999
        endif
csms$serial end

csms$create_decomp(grid_dh, <nx_l>, <0>)
csms$serial(<r_missing_data, out>:default=ignore)  begin              
        NTMIN = -1
        NTMAX = +1

        call get_systime(i4time_lapswind,a9_time,istatus)
        if(istatus .ne. 1)go to 999
        write(6,*)' systime = ',a9_time

        call get_directory('log',fname,log_len)
        if (log_len .le. 0 .or. log_len .gt. len_trim(fname)) then
           write(6,*) 'Invalid wind log directory length'
           go to 999
        endif
        open(15,file=fname(1:log_len)//'wind_stats.log'
     1      ,status='unknown',iostat=ios)
        if (ios .ne. 0) then
           write(6,*) 'Error opening wind statistics log'
           go to 999
        endif
        log_open = .true.

        call get_max_radars(max_radars,istatus)
	if (istatus .ne. 1) then
	   write (6,*) 'Error obtaining max_radars'
	   go to 999
	endif
	call get_meso_sao_pirep(N_MESO,N_SAO,N_PIREP,istatus)
	if (istatus .ne. 1) then
	   write (6,*) 'Error obtaining N_MESO, N_SAO, and N_PIREP'
	   go to 999
	endif
	call get_r_missing_data(r_missing_data,istatus)
	if (istatus .ne. 1) then
	   write (6,*) 'Error obtaining r_missing_data'
	   go to 999
	endif
	call get_i2_missing_data(i2_missing_data,istatus)
	if (istatus .ne. 1) then
	   write (6,*) 'Error obtaining i2_missing_data'
	   go to 999
	endif

	if (max_radars .lt. 0 .or. N_MESO .lt. 0 .or.
     1      N_SAO .lt. 0 .or. N_PIREP .lt. 0) then
	   write (6,*) 'Invalid wind observation counts'
	   go to 999
	endif

csms$serial end

        call lapswind_anal  (i4time_lapswind,NX_L,NY_L,NZ_L,
     1              NTMIN,NTMAX,
     1              max_radars,N_MESO,N_SAO,N_PIREP,
     1              r_missing_data,i2_missing_data,
     1              n_prods,
     1              i4time_array,
     1              j_status)

        if (j_status(6) .eq. 1 .and.
     1      i4time_array(6) .eq. i4time_lapswind .and.
     1      n_prods .gt. 0) then
           if (log_open) then
              close(15,iostat=ios)
              log_open = .false.
              if (ios .ne. 0) go to 999
           endif
           write(6,*) 'WIND_PRODUCER_SUCCESS'
           stop 0
        endif

999     continue
        if (log_open) then
           close(15,iostat=ios)
           log_open = .false.
        endif
        write(6,*) 'WIND_PRODUCER_FAILED'
        stop 1

csms$exit
        end
