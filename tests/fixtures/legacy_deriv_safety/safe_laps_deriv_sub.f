      subroutine laps_deriv_sub
      logical l_evap_radar, l_bogus_radar_w, l_flag_bogus_w
      integer mode_evap, istatus
      call get_deriv_parms(mode_evap,l_bogus_radar_w,istatus)
      l_evap_radar = .false.
      mode_evap = 0
      l_bogus_radar_w = .false.
      l_flag_bogus_w = .false.
      w_3d = r_missing_data
      call get_cloud_deriv(i4time,nx,ny,nz,clouds,cld_hts,
     1 temp,rh,hgt,pres,istat_ref,ref,dx,pcpmask,ibase,itop,
     1 iflag,slwc,cice,thresh,l_type,ctype,l_mvd,mvd,l_ice,
     1 icing,.false.,w_3d,istatus)
      if(.false.)then
        call get_radar_deriv(istatus)
      endif
      if(.false. .and. l_evap_radar)then
        call rfill_evap(mode_evap,istatus)
      endif
      end
