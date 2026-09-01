cdis    Forecast Systems Laboratory
cdis    NOAA/OAR/ERL/FSL
cdis    325 Broadway
cdis    Boulder, CO     80303
cdis
cdis    Forecast Research Division
cdis    Local Analysis and Prediction Branch
cdis    LAPS
cdis
cdis    This software and its documentation are in the public domain and
cdis    are furnished "as is."  The United States government, its
cdis    instrumentalities, officers, employees, and agents make no
cdis    warranty, express or implied, as to the usefulness of the software
cdis    and documentation for any purpose.  They assume no responsibility
cdis    (1) for the use of the software and documentation; or (2) to provide
cdis     technical support to users.
cdis
cdis    Permission to use, copy, modify, and distribute this software is
cdis    hereby granted, provided that the entire disclaimer notice appears
cdis    in all copies.  All modifications to this software must be clearly
cdis    documented, and are solely the responsibility of the agent making
cdis    the modifications.  If significant modifications or enhancements
cdis    are made to this software, the FSL Software Policy Manager
cdis    (softwaremgr@fsl.noaa.gov) should be notified.
cdis
cdis
cdis
cdis
cdis
cdis
cdis
        Subroutine Cloud_bogus_w_lgt_ct (dx, cloud_type, height, nk, w)

        use cloud_bal_cloud_profiles, only: build_multilayer_w_profile

!Original version October 1990.

!Modified May 1991 when we realized that a grid box is a lot bigger than
!any updraft.  We reduced the maximum vv in the parabolic profiles in cumulus
!clouds by a fairly large amount (30 m/s in 10 km Cu to 5 m/s), and the vv max
!for stratocumulus by a smaller amount (50 cm/s in 4-km Sc to 20 cm/s).

!  Modified June 2002 - Once again reduced the maximum cloud vv magnitude
!                       and made it dependent on grid spacing.  Also
!                       changed parabolic vv profile for cumuliform clouds
!                       to only go down to the cloud base, rather than 
!                       1/3rd of the cloud depth below base to try and
!                       and improve elevated convection cases.

!Can be used with either regular LAPS analysis grid or the cloud analysis grid.
        Implicit none
        Integer*4 nk, cloud_type(nk)
        Real*4 dx, height(nk), w(nk)

!The following specifies the maximum vv in two cloud types as functions
!of cloud depth.  Make parabolic vv profile, except for stratiform clouds,
!which get a constant value.  The values are tuned to give values that
!an NWP model would typically produce.  
! add lightning event 2019.03

        Real*4 vv_to_height_ratio_Cu
        Real*4 vv_to_height_ratio_Sc
        Real*4 vv_for_St
        Real*4 vv_to_height_ratio_Ct   !!! for lightning

        ! Values below are the max VVs expected on a 10km grid for a 
        ! cloud 10km deep
!       data vv_to_height_ratio_Cu /1./  ! Changed from 4.0 on 10 Apr 03 BLS   
!       data vv_to_height_ratio_Sc /0.1/ ! Changed from 0.5 on 10 Apr 03 BLS
!       data vv_for_St /.02/              ! Changed from 0.05 on 10 Apr 03 BLS
!       Adan add
!frl 20070928 start
!yhlee        data vv_to_height_ratio_Cu /0.5/  ! Changed from 1.0 on 10 Aug 03 BLS
!       data vv_to_height_ratio_Sc /0.05/ ! Changed from 0.1 on 10 Aug 03 BLS
!       data vv_for_St /.01/              ! Changed from 0.02 on 10 Aug 03 BLS

        Real*4 ratio, vv, Parabolic_vv_profile

        Integer*4 k, k1, kbase, ktop, profile_status
        Real*4 zbase, ztop

!   Cloud Type      /'  ','St','Sc','Cu','Ns','Ac','As','Cs','Ci','Cc','Cb','Ct'/
!   Integer Value     0     1    2    3    4    5    6    7    8    9   10   11


	character(len=100) :: env_vv_to_height_ratio_Cu = '   '
     &                      , env_vv_to_height_ratio_Sc = '   '
     &                      , env_vv_for_St = '   '
     &                      , env_vv_to_height_ratio_Ct = '   '

	call getenv('GA_VV_TO_HEIGHT_RATIO_CU',
     &                 env_vv_to_height_ratio_Cu)
	call getenv('GA_VV_TO_HEIGHT_RATIO_SC',
     &                 env_vv_to_height_ratio_Sc)
	call getenv('GA_VV_FOR_ST',
     &                 env_vv_for_St)
	call getenv('GA_VV_TO_HEIGHT_RATIO_CT',
     &                 env_vv_to_height_ratio_Ct)

	if ( env_vv_to_height_ratio_Cu(1:10) .eq. '          ' ) then
          print*, 
     &    'There is no GA_VV_TO_HEIGHT_RATIO_CU envirionmental variable'
          print*, 'GA_VV_TO_HEIGHT_RATIO_CU is set 0.5'
          env_vv_to_height_ratio_Cu(1:3) = '0.5'
        endif
	if ( env_vv_to_height_ratio_Sc(1:10) .eq. '          ' ) then
          print*, 
     &    'There is no GA_VV_TO_HEIGHT_RATIO_SC envirionmental variable'
          print*, 'GA_VV_TO_HEIGHT_RATIO_SC is set 0.05'
          env_vv_to_height_ratio_Sc(1:4) = '0.05'
        endif
	if ( env_vv_for_St(1:10) .eq. '          ' ) then
          print*, 
     &    'There is no GA_VV_FOR envirionmental variable'
          print*, 'GA_VV_FOR_ST is set 0.01'
          env_vv_for_St(1:4) = '0.01'
        endif
! for lightning
	if ( env_vv_to_height_ratio_Ct(1:10) .eq. '          ' ) then
          print*, 
     &    'There is no GA_VV_TO_HEIGHT_RATIO_CT envirionmental variable'
          print*, 'GA_VV_TO_HEIGHT_RATIO_CT(lightning) is set 1'
!          env_vv_to_height_ratio_Ct(1:3) = '1'   !!! test
          env_vv_to_height_ratio_Ct(1:3) = '0.5'      !!!! Same as Cu
        endif
! for lighitning

        read(env_vv_to_height_ratio_Cu, fmt=* ) vv_to_height_ratio_Cu
        print*, 'VV_TO_HEIGHT_RATIO_CU : ', vv_to_height_ratio_Cu

        read(env_vv_to_height_ratio_Sc, fmt=* ) vv_to_height_ratio_Sc
        print*, 'VV_TO_HEIGHT_RATIO_SC : ', vv_to_height_ratio_Sc

        read(env_vv_for_St, fmt=* ) vv_for_St
        print*, 'VV_FOR_ST : ', vv_for_St

! for lightning
        read(env_vv_to_height_ratio_Ct, fmt=* ) vv_to_height_ratio_Ct
        print*, 'VV_TO_HEIGHT_RATIO_CT : ', vv_to_height_ratio_Ct
! for lighitning

!frl 20070928 end  

!       Detect every contiguous cloud layer first, including a layer ending
!       at nk.  Each layer is then profiled independently.  Convective layers
!       ascend; precipitating stratiform (Ns) layers include a lower descent
!       lobe and upper ascent.  Clear levels retain the missing-data value.
        call build_multilayer_w_profile(dx,cloud_type,height,
     1       max(vv_to_height_ratio_Cu,vv_to_height_ratio_Ct),
     1       vv_to_height_ratio_Sc,vv_for_St,1E37,w,profile_status)
        if(profile_status .ne. 1)then
          write(6,*)'Cloud profile rejected: invalid height/grid metadata'
          do k = 1,nk
            w(k) = 1E37
          enddo
        endif

        Return
        End

!-------------------------------------------------------------------
!        Real*4 Function Parabolic_vv_profile (zbase, ztop, ratio, z)
!The vertical velocity is zero at cloud top, peaks one third of the way up
!from the base, and extends below the base by one third of the cloud depth.
!
!  JUNE 2002 - No longer extending profile to below cloud base.

!        Implicit none
!        Real*4 zbase, ztop, ratio, z
!        Real*4 depth, vvmax, vvspan, halfspan, height_vvmax, x
!
!        depth = ztop - zbase
!        If (depth .le. 0.) then
!         Parabolic_vv_profile = 0.
!         Return
!        End if
!
!        vvmax = ratio * depth
!        vvspan = depth * 1.1    
!        halfspan = vvspan / 2.
!        height_vvmax = ztop - halfspan
!        x = -vvmax/(halfspan*halfspan)
!
!        Parabolic_vv_profile = x * (z-height_vvmax)**2 + vvmax
!
!        Return
!        End
