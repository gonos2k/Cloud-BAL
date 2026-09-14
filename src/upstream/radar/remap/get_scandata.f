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
        subroutine  get_scandata(
     :          i_tilt,             ! Input  (Integer*4)
     :          r_missing_data,     ! Input  (Real*4)
     :          max_rays,           ! Input  (Integer*4)
     :          n_rays,             ! Output (Integer*4)
     :          n_gates,            ! Output (Integer*4)
     :          gate_spacing_m,     ! Output (Real*4)
     :          elevation_deg,      ! Output (Real*4)
     :          i_scan_mode,        ! Output (Integer*4)
     :          v_nyquist_tilt,     ! Output (Real*4)
     :          v_nyquist_ray,      ! Output (Real*4 array)
     :          istatus )           ! Output (Integer*4)

c
c     PURPOSE:
c
c       Get info for radar data.
c
      implicit none
c
c     Input variables
c
      integer*4 i_tilt
      real*4 r_missing_data
      integer*4 max_rays
c
c     Output variables
c
      integer*4 n_rays
      integer*4 n_gates
      real*4 gate_spacing_m
      real*4 elevation_deg
      integer*4 i_scan_mode
      real*4 v_nyquist_tilt
      real*4 v_nyquist_ray(max_rays)
      integer*4 istatus
c
c     Include file
c
      include 'remap_dims.inc'
      include 'remap_buffer.cmn'
      include 'remap_geometry.cmn'
c
c     Misc internal variables
c
      integer i
c
      n_rays = n_rays_cmn
      n_gates = n_vel_gates_cmn
      gate_spacing_m = gsp_vel_m_cmn
      elevation_deg = elev_cmn

c     This consumer supports the normalized decoder geometry only.  The
c     values come from the tilt metadata through fill_common; reject a
c     different geometry before any ray/gate work is attempted.
      IF (lut_geometry_ready_cmn .ne. 1 .or.
     :    abs(first_vel_m_cmn-lut_first_gate_m_cmn) .gt. 0.01 .or.
     :    abs(gate_spacing_m-lut_gate_spacing_m_cmn) .gt. 0.01 .or.
     :    n_ref_gates_cmn .ne. n_vel_gates_cmn .or.
     :    n_gates .ne. MAX_REF_GATES .or.
     :    abs(gsp_ref_m_cmn-gsp_vel_m_cmn) .gt. 0.01 .or.
     :    abs(gate_spacing_m-GATE_SPACING_M) .gt. 0.01 .or.
     :    gate_spacing_m .le. 0. .or. gate_spacing_m .gt. 1000. .or.
     :    first_ref_m_cmn .lt. 0. .or. first_ref_m_cmn .ge. 1000. .or.
     :    first_vel_m_cmn .lt. 0. .or. first_vel_m_cmn .ge. 1000. .or.
     :    abs(first_ref_m_cmn-first_vel_m_cmn) .gt. 0.01) THEN
        write(6,*) ' Unsupported radar geometry in get_scandata:',
     :      n_ref_gates_cmn,n_vel_gates_cmn,gsp_ref_m_cmn,gsp_vel_m_cmn,
     :      first_ref_m_cmn,first_vel_m_cmn,
     :      lut_geometry_ready_cmn,lut_first_gate_m_cmn,
     :      lut_gate_spacing_m_cmn
        n_rays = 0
        n_gates = 0
        istatus = 0
        RETURN
      END IF
      i_scan_mode = 1

c     The remap work arrays are smaller than the persistent radar common
c     block.  Reject a malformed count before indexing the caller arrays.
      IF (n_rays .lt. 1 .or. n_rays .gt. max_rays) THEN
        write(6,*) ' Invalid radar ray count in get_scandata: ',n_rays
        n_rays = 0
        n_gates = 0
        istatus = 0
        RETURN
      END IF

      IF (n_gates .lt. 1 .or. n_gates .gt. MAX_REF_GATES) THEN
        write(6,*) ' Invalid radar gate count in get_scandata: ',n_gates
        n_rays = 0
        n_gates = 0
        istatus = 0
        RETURN
      END IF
c
c     Transfer nyquist info from common to output array
c
      DO 100 i = 1,n_rays
        IF (v_nyquist_ray_a_cmn(i) .eq. 0.) THEN
          v_nyquist_ray(i) = r_missing_data
        ELSE
          v_nyquist_ray(i) = v_nyquist_ray_a_cmn(i)
        END IF
  100 CONTINUE
c
c     Check all nyquists in this tilt.
c     If they are all the same, report that as the tilt nyquist,
c     else report r_missing
c
      v_nyquist_tilt = v_nyquist_ray(1)
      DO 200 i = 1,n_rays
        IF (v_nyquist_ray(i) .eq. r_missing_data .or.
     :      v_nyquist_ray(i) .le. 0. .or.
     :      v_nyquist_ray(i) .ge. 1000.) THEN
          v_nyquist_tilt = r_missing_data
          GO TO 999
        ELSE IF (v_nyquist_ray(i) .ne. v_nyquist_tilt) THEN
          v_nyquist_tilt = r_missing_data
          GO TO 999
        END IF
  200 CONTINUE

  999 CONTINUE

      istatus = 1
      RETURN
      END
