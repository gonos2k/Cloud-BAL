! Isolated Cloud-BAL copy of the KLAPS Cf/Radial decoder.
!
! This source deliberately keeps the legacy 800-radial by 920-gate output
! contract.  Inputs with more than 920 gates are safely clipped to the output
! contract and the output records both gate counts and the clipping flag.  The
! source is not wired into the operational KLAPS tree.
program RDR_PREP_EXPRESS
  use, intrinsic :: ieee_arithmetic, only: ieee_is_finite
  use, intrinsic :: iso_c_binding, only: c_char, c_int, c_null_char
  implicit none
  include 'netcdf.inc'

  integer, parameter :: radial = 800, Z_bin = 920, V_bin = 920
  integer, parameter :: radarNamelen = 8, siteNameLen = 16
  real, parameter :: NODATA = 131072.0

  integer :: nt, np, nr, ns, nray, nbin, nbin2
  integer :: ncid, nvarid, ik, i, j, ij
  integer :: time_dim, points_dim, range_dim, sweep_dim
  integer :: ray_cursor, point_cursor, ray_start, ray_end
  integer(kind=8) :: total_points, point_cursor_8, expected_point
  integer :: idimid(3), rad_did, zbin_did, vbin_did, rn_did, sn_did
  integer :: z_vd, v_vd, w_vd, en_vd, ea_vd, nr_vd, ra_vd, re_vd, rt_vd
  integer :: sn_vd, rn_vd, sla_vd, slo_vd, slt_vd, vc_vd, es_vd, ee_vd
  integer :: un_vd, uz_vd, uv_vd, gsz_vd, gsv_vd, ngz_vd, ngv_vd
  integer :: res_vd, nyq_vd, cal_vd, aaf_vd, pow_vd
  integer :: en_rge(2), nr_rge(2), ng_rge(2), nv_rge(2)

  real :: siteLat, siteLon, siteAlt
  real :: zfac, vfac, wfac, zoff, voff, woff
  real :: zmiss, vmiss, wmiss
  real :: gate_range, first_gate_range, gate_spacing
  character(len=64) :: width_units
  real :: Azim(radial), elev(radial)
  real, allocatable :: nc_elev(:), radialElev(:), radialAzim(:)
  real, allocatable :: DBZ(:,:), VEL(:,:), WID(:,:), range_values(:)
  real, allocatable :: nyq_vel(:)
  real, allocatable :: z_rge(:), v_rge(:), w_rge(:)
  double precision :: EPOTIM, time_epoch, coverage_start_epoch, coverage_end_epoch
  double precision :: rtim(radial), rdrt(radial)
  double precision, allocatable :: radialTime(:)

  character(len=255) :: FileName, NC_DAOU, infile
  character(len=9) :: JULDATE
  character(len=64) :: EPODATE
  character(len=3) :: RDRNAME
  character(len=2) :: numk
  character(len=255) :: time_units, time_calendar, coverage_start, coverage_end
  integer, allocatable :: nrays(:), nbins(:), sweep_start(:), sweep_end(:)
  integer, allocatable :: ray_start_index(:), ray_n_gates(:)
  integer(kind=2), allocatable :: Z(:), V(:), W(:)

  call required_argument(1, infile, 'input file')
  call required_environment('NC_DAOU', NC_DAOU)
  call required_environment('JULDATE', JULDATE)
  call required_environment('EPODATE', EPODATE)
  call required_environment('RDRNAME', RDRNAME)
  read(EPODATE, *, iostat=i) EPOTIM
  if (i /= 0 .or. .not.ieee_is_finite(real(EPOTIM))) then
    call reject('EPODATE is not a finite epoch value')
  end if

  write(*, '(A,A)') 'open: ', trim(infile)
  call nc_check(nf_open(trim(infile), nf_nowrite, ncid), 'nf_open input')
  call read_dimension(ncid, 'time', time_dim, nt)
  call read_dimension(ncid, 'n_points', points_dim, np)
  call read_dimension(ncid, 'range', range_dim, nr)
  call read_dimension(ncid, 'sweep', sweep_dim, ns)

  if (nt <= 0 .or. np <= 0 .or. nr <= 1) then
    call reject('time, n_points, and range dimensions must be positive')
  end if
  if (ns <= 0 .or. ns > 100) then
    call reject('sweep dimension is outside the supported 1..100 range')
  end if
  if (nt > radial * ns) then
    call reject('time dimension exceeds the fixed radial contract')
  end if

  allocate(Z(np), V(np), W(np), nc_elev(nt), radialAzim(nt))
  allocate(radialTime(nt), radialElev(ns), nrays(ns), nbins(ns))
  allocate(nyq_vel(ns), range_values(nr), sweep_start(ns), sweep_end(ns))
  allocate(ray_start_index(nt), ray_n_gates(nt))

  call require_1d_var(ncid, 'DBZH', points_dim, np, nf_short, nvarid)
  call nc_check(nf_get_var_int2(ncid, nvarid, Z), 'read DBZH')
  call require_text_attribute(ncid, nvarid, 'units', 'dBZ', 'DBZH')
  call required_real_attribute(ncid, nvarid, 'scale_factor', zfac, 'DBZH')
  call optional_real_attribute(ncid, nvarid, 'add_offset', zoff, 'DBZH')
  call required_real_attribute(ncid, nvarid, '_FillValue', zmiss, 'DBZH')

  call require_1d_var(ncid, 'VELH', points_dim, np, nf_short, nvarid)
  call nc_check(nf_get_var_int2(ncid, nvarid, V), 'read VELH')
  call require_text_attribute(ncid, nvarid, 'units', 'm/s', 'VELH')
  call required_real_attribute(ncid, nvarid, 'scale_factor', vfac, 'VELH')
  call optional_real_attribute(ncid, nvarid, 'add_offset', voff, 'VELH')
  call required_real_attribute(ncid, nvarid, '_FillValue', vmiss, 'VELH')

  call require_1d_var(ncid, 'WIDTHH', points_dim, np, nf_short, nvarid)
  call nc_check(nf_get_var_int2(ncid, nvarid, W), 'read WIDTHH')
  call read_text_attribute(ncid, nvarid, 'units', width_units, 'WIDTHH')
  call required_real_attribute(ncid, nvarid, 'scale_factor', wfac, 'WIDTHH')
  call optional_real_attribute(ncid, nvarid, 'add_offset', woff, 'WIDTHH')
  call required_real_attribute(ncid, nvarid, '_FillValue', wmiss, 'WIDTHH')

  call require_positive_scale(zfac, 'DBZH scale_factor')
  call require_positive_scale(vfac, 'VELH scale_factor')
  call require_positive_scale(wfac, 'WIDTHH scale_factor')
  if (.not.ieee_is_finite(zoff) .or. .not.ieee_is_finite(voff) .or. &
      .not.ieee_is_finite(woff)) then
    call reject('moment add_offset is not finite')
  end if

  call require_1d_var(ncid, 'elevation', time_dim, nt, nf_real, nvarid)
  call require_text_attribute(ncid, nvarid, 'units', 'degree', 'elevation')
  call nc_check(nf_get_var_real(ncid, nvarid, nc_elev), 'read elevation')
  call require_1d_var(ncid, 'azimuth', time_dim, nt, nf_real, nvarid)
  call require_text_attribute(ncid, nvarid, 'units', 'degree', 'azimuth')
  call nc_check(nf_get_var_real(ncid, nvarid, radialAzim), 'read azimuth')
  call require_1d_var(ncid, 'time', time_dim, nt, nf_double, nvarid)
  call nc_check(nf_get_var_double(ncid, nvarid, radialTime), 'read time')
  call read_time_contract(ncid, nvarid, time_epoch, time_units, time_calendar, &
                          coverage_start, coverage_end, coverage_start_epoch, &
                          coverage_end_epoch)
  call validate_juldate(JULDATE, time_units(15:))
  if (abs(EPOTIM - time_epoch) > 1.0d-6) then
    call reject('EPODATE does not match the CF time origin')
  end if
  EPOTIM = time_epoch
  call require_1d_var(ncid, 'range', range_dim, nr, nf_real, nvarid)
  call require_text_attribute(ncid, nvarid, 'units', 'meters', 'range')
  call nc_check(nf_get_var_real(ncid, nvarid, range_values), 'read range')

  call require_scalar_var(ncid, 'latitude', nvarid)
  call nc_check(nf_get_var_real(ncid, nvarid, siteLat), 'read latitude')
  call require_scalar_var(ncid, 'longitude', nvarid)
  call nc_check(nf_get_var_real(ncid, nvarid, siteLon), 'read longitude')
  call require_scalar_var(ncid, 'altitude', nvarid)
  call nc_check(nf_get_var_real(ncid, nvarid, siteAlt), 'read altitude')

  call require_1d_var(ncid, 'nyquist_velocity', sweep_dim, ns, nf_real, nvarid)
  call require_text_attribute(ncid, nvarid, 'units', 'm/s', 'nyquist_velocity')
  call nc_check(nf_get_var_real(ncid, nvarid, nyq_vel), &
                'read nyquist_velocity')
  if (any(.not.ieee_is_finite(nyq_vel)) .or. any(nyq_vel <= 0.0)) then
    call reject('nyquist_velocity contains nonfinite or nonpositive values')
  end if

  call require_1d_var(ncid, 'rays', sweep_dim, ns, nf_int, nvarid)
  call nc_check(nf_get_var_int(ncid, nvarid, nrays), 'read rays')
  call require_1d_var(ncid, 'bins', sweep_dim, ns, nf_int, nvarid)
  call nc_check(nf_get_var_int(ncid, nvarid, nbins), 'read bins')
  call require_1d_var(ncid, 'sweep_start_ray_index', sweep_dim, ns, nf_int, nvarid)
  call nc_check(nf_get_var_int(ncid, nvarid, sweep_start), &
                'read sweep_start_ray_index')
  call require_1d_var(ncid, 'sweep_end_ray_index', sweep_dim, ns, nf_int, nvarid)
  call nc_check(nf_get_var_int(ncid, nvarid, sweep_end), &
                'read sweep_end_ray_index')
  call require_1d_var(ncid, 'ray_start_index', time_dim, nt, nf_int, nvarid)
  call nc_check(nf_get_var_int(ncid, nvarid, ray_start_index), &
                'read ray_start_index')
  call require_1d_var(ncid, 'ray_n_gates', time_dim, nt, nf_int, nvarid)
  call nc_check(nf_get_var_int(ncid, nvarid, ray_n_gates), &
                'read ray_n_gates')
  call nc_check(nf_close(ncid), 'close input')

  call require_finite_real(nc_elev, 'elevation')
  call require_finite_real(radialAzim, 'azimuth')
  call require_finite_double(radialTime, 'time')
  if (time_epoch + minval(radialTime) < coverage_start_epoch - 1.0d-6 .or. &
      time_epoch + maxval(radialTime) > coverage_end_epoch + 1.0d-6) then
    call reject('ray epochs fall outside time coverage metadata')
  end if
  call require_finite_real(range_values, 'range')
  if (.not.ieee_is_finite(siteLat) .or. .not.ieee_is_finite(siteLon) .or. &
      .not.ieee_is_finite(siteAlt)) then
    call reject('site coordinates contain a nonfinite value')
  end if
  if (siteLat < -90.0 .or. siteLat > 90.0 .or. siteLon < -180.0 .or. &
      siteLon > 180.0) then
    call reject('site latitude or longitude is outside physical bounds')
  end if
  if (nt > 1 .and. any(radialTime(2:nt) < radialTime(1:nt-1))) then
    call reject('radial time decreases across sweeps')
  end if
  if (any(range_values(2:nr) <= range_values(1:nr-1))) then
    call reject('range coordinate is not strictly increasing')
  end if
  first_gate_range = range_values(1)
  gate_spacing = range_values(2) - range_values(1)
  if (first_gate_range < 0.0 .or. gate_spacing <= 0.0) then
    call reject('range coordinate has invalid first gate or spacing')
  end if
  if (nr > 2 .and. any(abs((range_values(3:nr) - range_values(2:nr-1)) - &
      gate_spacing) > 1.0e-3)) then
    call reject('range coordinate is not uniformly spaced')
  end if

  total_points = 0_8
  ray_cursor = 0
  point_cursor_8 = 0_8
  do ik = 1, ns
    if (nrays(ik) <= 0 .or. nrays(ik) > radial) then
      call reject('rays value is outside the fixed radial contract')
    end if
    if (nbins(ik) <= 0 .or. nbins(ik) > nr) then
      call reject('bins value is outside the input range dimension')
    end if
    if (sweep_start(ik) /= ray_cursor .or. &
        sweep_end(ik) /= ray_cursor + nrays(ik) - 1) then
      call reject('sweep ray index metadata does not match rays')
    end if
    total_points = total_points + int(nrays(ik), 8) * int(nbins(ik), 8)
    ray_cursor = ray_cursor + nrays(ik)
    point_cursor_8 = point_cursor_8 + int(nrays(ik), 8) * int(nbins(ik), 8)
  end do
  if (ray_cursor /= nt) then
    call reject('sum(rays) does not equal time dimension')
  end if
  if (total_points /= int(np, 8)) then
    call reject('sum(rays*bins) does not equal n_points dimension')
  end if

  ray_cursor = 0
  point_cursor_8 = 0_8
  do ik = 1, ns
    do j = 1, nrays(ik)
      expected_point = point_cursor_8 + int(j - 1, 8) * int(nbins(ik), 8)
      if (ray_start_index(ray_cursor + j) /= expected_point .or. &
          ray_n_gates(ray_cursor + j) /= nbins(ik)) then
        call reject('ray_start_index/ray_n_gates do not match packed moments')
      end if
    end do
    ray_cursor = ray_cursor + nrays(ik)
    point_cursor_8 = point_cursor_8 + int(nrays(ik), 8) * int(nbins(ik), 8)
  end do
  write(*, '(A,I0,A,I0)') 'DECODER_VALIDATED_INPUT sweeps=', ns, &
    ' rays=', nt

  call set_packed_range(zfac, zoff, z_rge)
  call set_packed_range(vfac, voff, v_rge)
  call set_packed_range(wfac, woff, w_rge)
  en_rge = (/1, 25/)
  nr_rge = (/0, radial/)
  ng_rge = (/0, Z_bin/)
  nv_rge = (/0, V_bin/)

  ray_cursor = 0
  point_cursor = 0
  do ik = 1, ns
    write(numk, '(I2.2)') ik
    nray = nrays(ik)
    nbin = nbins(ik)
    ray_start = ray_cursor + 1
    ray_end = ray_cursor + nray
    nbin2 = min(nbin, V_bin)
    radialElev(ik) = nc_elev(ray_end)
    if (radialElev(ik) < -90.0 .or. radialElev(ik) > 90.0) then
      call reject('elevation is outside the physical angle bounds')
    end if

    Azim = 0.0
    Azim(1:nray) = radialAzim(ray_start:ray_end)
    elev = 0.0
    elev(1:nray) = nc_elev(ray_start:ray_end)
    if (any(elev(1:nray) < -90.0) .or. any(elev(1:nray) > 90.0)) then
      call reject('radial elevation is outside the physical angle bounds')
    end if
    rdrt = 0.0d0
    rdrt(1:nray) = radialTime(ray_start:ray_end)
    rtim = 0.0d0
    do i = 1, nray
      rtim(i) = EPOTIM + rdrt(i)
    end do
    if (nray > 1 .and. any(rtim(2:nray) < rtim(1:nray-1))) then
      call reject('radial time decreases inside a sweep')
    end if

    allocate(DBZ(Z_bin, radial), VEL(V_bin, radial), WID(V_bin, radial))
    DBZ = NODATA
    VEL = NODATA
    WID = NODATA
    do j = 1, nray
      ij = point_cursor + nbin * (j - 1) + 1
      do i = 1, nbin2
        if (real(Z(ij)) /= zmiss) DBZ(i,j) = real(Z(ij))*zfac + zoff
        if (real(V(ij)) /= vmiss) VEL(i,j) = real(V(ij))*vfac + voff
        if (real(W(ij)) /= wmiss) WID(i,j) = real(W(ij))*wfac + woff
        ij = ij + 1
      end do
    end do
    if (nray < radial) then
      DBZ(:,nray+1:radial) = 0.0
      VEL(:,nray+1:radial) = 0.0
      WID(:,nray+1:radial) = 0.0
    end if
    if (any(.not.ieee_is_finite(DBZ)) .or. any(.not.ieee_is_finite(VEL)) .or. &
        any(.not.ieee_is_finite(WID))) then
      call reject('decoded moment contains a nonfinite value')
    end if

    gate_range = (first_gate_range + gate_spacing * real(nbin2 - 1)) / 1000.0
    FileName = trim(NC_DAOU)//'/RADR/ouda/'//trim(RDRNAME)//'/'// &
      trim(JULDATE)//'_elev'//trim(numk)
    write(*, '(A,A)') 'write: ', trim(FileName)
    call write_sweep(trim(FileName), ik, nray, nbin2, nbin, gate_range, width_units, &
                     time_units, time_calendar, coverage_start, coverage_end)
    deallocate(DBZ, VEL, WID)

    ray_cursor = ray_cursor + nray
    point_cursor = point_cursor + nray * nbin
  end do

  deallocate(Z, V, W, nc_elev, radialElev, radialAzim, radialTime)
  deallocate(nrays, nbins, nyq_vel, range_values, sweep_start, sweep_end)
  deallocate(ray_start_index, ray_n_gates, z_rge, v_rge, w_rge)
  write(*, '(A)') 'DECODER_COMPLETE raw moments only; no dealias/fall-speed/target authority'

contains

  subroutine write_sweep(path, sweep_number, nrays_out, nbins_out, source_nbins, range_km, &
                         width_units, source_time_units, source_calendar, source_coverage_start, &
                         source_coverage_end)
    character(len=*), intent(in) :: path
    integer, intent(in) :: sweep_number, nrays_out, nbins_out, source_nbins
    real, intent(in) :: range_km
    character(len=*), intent(in) :: width_units, source_time_units, source_calendar
    character(len=*), intent(in) :: source_coverage_start, source_coverage_end
    real :: scalar_real(1)
    integer :: scalar_int(1)
    real :: ea_rge(2), ra_rge(2), re_rge(2), ca_rge(2)
    character(len=radarNamelen) :: radar_name_text
    character(len=siteNameLen) :: site_name_text
    character(len=512) :: temporary_path

    temporary_path = trim(path)//'.tmp'
    call nc_check(nf_create(trim(temporary_path), nf_noclobber, ncid), 'nf_create output temporary')
    call nc_check(nf_def_dim(ncid, 'radial', radial, rad_did), 'define radial')
    call nc_check(nf_def_dim(ncid, 'Z_bin', Z_bin, zbin_did), 'define Z_bin')
    call nc_check(nf_def_dim(ncid, 'V_bin', V_bin, vbin_did), 'define V_bin')
    call nc_check(nf_def_dim(ncid, 'radarNameLen', radarNamelen, rn_did), &
                  'define radarNameLen')
    call nc_check(nf_def_dim(ncid, 'siteNameLen', siteNameLen, sn_did), &
                  'define siteNameLen')

    idimid(1) = zbin_did
    idimid(2) = rad_did
    call nc_check(nf_def_var(ncid, 'Z', nf_real, 2, idimid, z_vd), 'define Z')
    call put_text_att(ncid, z_vd, 'long_name', 'Reflectivity')
    call put_text_att(ncid, z_vd, 'units', 'dBZ')
    call put_real_att(ncid, z_vd, 'valid_range', z_rge)
    call put_real_scalar_att(ncid, z_vd, 'below_threshold', 0.0)
    call put_real_scalar_att(ncid, z_vd, 'range_ambiguous', 1.0)
    call put_real_scalar_att(ncid, z_vd, '_FillValue', NODATA)

    idimid(1) = vbin_did
    call nc_check(nf_def_var(ncid, 'V', nf_real, 2, idimid, v_vd), 'define V')
    call put_text_att(ncid, v_vd, 'long_name', 'Velocity')
    call put_text_att(ncid, v_vd, 'units', 'meter/second')
    call put_real_att(ncid, v_vd, 'valid_range', v_rge)
    call put_real_scalar_att(ncid, v_vd, 'below_threshold', -40.0)
    call put_real_scalar_att(ncid, v_vd, 'range_ambiguous', 1.0)
    call put_real_scalar_att(ncid, v_vd, '_FillValue', NODATA)

    call nc_check(nf_def_var(ncid, 'W', nf_real, 2, idimid, w_vd), 'define W')
    call put_text_att(ncid, w_vd, 'long_name', 'Spectrum Width')
    call put_text_att(ncid, w_vd, 'units', trim(width_units))
    call put_real_att(ncid, w_vd, 'valid_range', w_rge)
    call put_real_scalar_att(ncid, w_vd, 'below_threshold', -20.0)
    call put_real_scalar_att(ncid, w_vd, 'range_ambiguous', 1.0)
    call put_real_scalar_att(ncid, w_vd, '_FillValue', NODATA)

    call nc_check(nf_def_var(ncid, 'elevationNumber', nf_short, 0, idimid, en_vd), &
                  'define elevationNumber')
    call put_text_att(ncid, en_vd, 'long_name', 'Elevation number')
    call put_text_att(ncid, en_vd, 'units', 'count')
    call put_int_att(ncid, en_vd, 'valid_range', en_rge)

    ea_rge = (/-90.0, 90.0/)
    call nc_check(nf_def_var(ncid, 'elevationAngle', nf_real, 0, idimid, ea_vd), &
                  'define elevationAngle')
    call put_text_att(ncid, ea_vd, 'long_name', 'Elevation angle')
    call put_text_att(ncid, ea_vd, 'units', 'degree')
    call put_text_att(ncid, ea_vd, 'history', 'last radial elevation')
    call put_real_att(ncid, ea_vd, 'valid_range', ea_rge)

    nr_rge = (/0, radial/)
    call nc_check(nf_def_var(ncid, 'numRadials', nf_short, 0, idimid, nr_vd), &
                  'define numRadials')
    call put_text_att(ncid, nr_vd, 'long_name', 'Number of radials')
    call put_int_att(ncid, nr_vd, 'valid_range', nr_rge)

    ra_rge = (/0.0, 360.0/)
    call nc_check(nf_def_var(ncid, 'radialAzim', nf_real, 1, rad_did, ra_vd), &
                  'define radialAzim')
    call put_text_att(ncid, ra_vd, 'long_name', 'Radial azimuth angle')
    call put_text_att(ncid, ra_vd, 'units', 'degree')
    call put_real_att(ncid, ra_vd, 'valid_range', ra_rge)

    re_rge = (/-90.0, 90.0/)
    call nc_check(nf_def_var(ncid, 'radialElev', nf_real, 1, rad_did, re_vd), &
                  'define radialElev')
    call put_text_att(ncid, re_vd, 'long_name', 'Radial elevation angle')
    call put_text_att(ncid, re_vd, 'units', 'degree')
    call put_real_att(ncid, re_vd, 'valid_range', re_rge)

    call nc_check(nf_def_var(ncid, 'radialTime', nf_double, 1, rad_did, rt_vd), &
                  'define radialTime')
    call put_text_att(ncid, rt_vd, 'long_name', 'Time of radial')
    call put_text_att(ncid, rt_vd, 'units', 'seconds since 1970-1-1 00:00:00.00')

    call nc_check(nf_def_var(ncid, 'siteName', nf_char, 1, sn_did, sn_vd), &
                  'define siteName')
    call put_text_att(ncid, sn_vd, 'long_name', 'Long name of the radar site')
    call nc_check(nf_def_var(ncid, 'radarName', nf_char, 1, rn_did, rn_vd), &
                  'define radarName')
    call put_text_att(ncid, rn_vd, 'long_name', 'Official name of the radar')

    call nc_check(nf_def_var(ncid, 'siteLat', nf_real, 0, idimid, sla_vd), 'define siteLat')
    call put_text_att(ncid, sla_vd, 'long_name', 'Latitude of site')
    call put_text_att(ncid, sla_vd, 'units', 'degrees_north')
    call nc_check(nf_def_var(ncid, 'siteLon', nf_real, 0, idimid, slo_vd), 'define siteLon')
    call put_text_att(ncid, slo_vd, 'long_name', 'Longitude of site')
    call put_text_att(ncid, slo_vd, 'units', 'degrees_east')
    call nc_check(nf_def_var(ncid, 'siteAlt', nf_real, 0, idimid, slt_vd), 'define siteAlt')
    call put_text_att(ncid, slt_vd, 'long_name', 'Altitude of site above mean sea level')
    call put_text_att(ncid, slt_vd, 'units', 'meter')

    call nc_check(nf_def_var(ncid, 'VCP', nf_short, 0, idimid, vc_vd), 'define VCP')
    call put_text_att(ncid, vc_vd, 'long_name', 'Volume Coverage Pattern')
    call put_text_att(ncid, vc_vd, 'units', 'count')
    call nc_check(nf_def_var(ncid, 'esStartTime', nf_double, 0, idimid, es_vd), &
                  'define esStartTime')
    call put_text_att(ncid, es_vd, 'long_name', 'Start time of elevation scan')
    call put_text_att(ncid, es_vd, 'units', 'seconds since 1970-1-1 00:00:00.00')
    call nc_check(nf_def_var(ncid, 'esEndTime', nf_double, 0, idimid, ee_vd), &
                  'define esEndTime')
    call put_text_att(ncid, ee_vd, 'long_name', 'End time of elevation scan')
    call put_text_att(ncid, ee_vd, 'units', 'seconds since 1970-1-1 00:00:00.00')

    call nc_check(nf_def_var(ncid, 'unambigRange', nf_real, 0, idimid, un_vd), &
                  'define unambigRange')
    call put_text_att(ncid, un_vd, 'long_name', 'Range to last gate')
    call put_text_att(ncid, un_vd, 'units', 'kilometer')
    call nc_check(nf_def_var(ncid, 'firstGateRangeZ', nf_real, 0, idimid, uz_vd), &
                  'define firstGateRangeZ')
    call put_text_att(ncid, uz_vd, 'long_name', 'Range to 1st Reflectivity gate')
    call put_text_att(ncid, uz_vd, 'units', 'meter')
    call nc_check(nf_def_var(ncid, 'firstGateRangeV', nf_real, 0, idimid, uv_vd), &
                  'define firstGateRangeV')
    call put_text_att(ncid, uv_vd, 'long_name', 'Range to 1st Doppler gate')
    call put_text_att(ncid, uv_vd, 'units', 'meter')
    call nc_check(nf_def_var(ncid, 'gateSizeZ', nf_real, 0, idimid, gsz_vd), &
                  'define gateSizeZ')
    call put_text_att(ncid, gsz_vd, 'long_name', 'Reflectivity gate spacing')
    call put_text_att(ncid, gsz_vd, 'units', 'meter')
    call nc_check(nf_def_var(ncid, 'gateSizeV', nf_real, 0, idimid, gsv_vd), &
                  'define gateSizeV')
    call put_text_att(ncid, gsv_vd, 'long_name', 'Doppler gate spacing')
    call put_text_att(ncid, gsv_vd, 'units', 'meter')

    call nc_check(nf_def_var(ncid, 'numGatesZ', nf_short, 0, idimid, ngz_vd), &
                  'define numGatesZ')
    call put_text_att(ncid, ngz_vd, 'long_name', 'Number of reflectivity gates')
    call put_int_att(ncid, ngz_vd, 'valid_range', ng_rge)
    call nc_check(nf_def_var(ncid, 'numGatesV', nf_short, 0, idimid, ngv_vd), &
                  'define numGatesV')
    call put_text_att(ncid, ngv_vd, 'long_name', 'Number of Doppler gates')
    call put_int_att(ncid, ngv_vd, 'valid_range', nv_rge)

    call nc_check(nf_def_var(ncid, 'resolutionV', nf_real, 0, idimid, res_vd), &
                  'define resolutionV')
    call put_text_att(ncid, res_vd, 'long_name', 'Doppler velocity resolution')
    call put_text_att(ncid, res_vd, 'units', 'meter/second')
    call nc_check(nf_def_var(ncid, 'nyquist', nf_real, 0, idimid, nyq_vd), &
                  'define nyquist')
    call put_text_att(ncid, nyq_vd, 'long_name', 'Nyquist velocity')
    call put_text_att(ncid, nyq_vd, 'units', 'meter/second')

    ca_rge = (/-50.0, 50.0/)
    call nc_check(nf_def_var(ncid, 'calibConst', nf_real, 0, idimid, cal_vd), &
                  'define calibConst')
    call put_text_att(ncid, cal_vd, 'long_name', 'System gain calibration constant')
    call put_text_att(ncid, cal_vd, 'units', 'dB')
    call put_real_att(ncid, cal_vd, 'valid_range', ca_rge)
    call nc_check(nf_def_var(ncid, 'atmosAttenFactor', nf_real, 0, idimid, aaf_vd), &
                  'define atmosAttenFactor')
    call put_text_att(ncid, aaf_vd, 'long_name', 'Atmospheric attenuation factor')
    call put_text_att(ncid, aaf_vd, 'units', 'dB/kilometer')
    call nc_check(nf_def_var(ncid, 'powDiffThreshold', nf_real, 0, idimid, pow_vd), &
                  'define powDiffThreshold')
    call put_text_att(ncid, pow_vd, 'long_name', 'Range de-aliasing threshold')
    call put_text_att(ncid, pow_vd, 'units', 'dB')

    call put_text_att(ncid, nf_global, 'decoder_contract', &
                      'cloud_bal_radar_decoder_raw_moments_v1')
    call put_text_att(ncid, nf_global, 'authority', 'RAW_INPUT_ONLY')
    call put_text_att(ncid, nf_global, 'source_time_units', trim(source_time_units))
    call put_text_att(ncid, nf_global, 'source_time_calendar', trim(source_calendar))
    call put_text_att(ncid, nf_global, 'source_time_coverage_start', trim(source_coverage_start))
    call put_text_att(ncid, nf_global, 'source_time_coverage_end', trim(source_coverage_end))
    call put_int_scalar_att(ncid, nf_global, 'source_gate_count', source_nbins)
    call put_int_scalar_att(ncid, nf_global, 'output_gate_count', nbins_out)
    call put_int_scalar_att(ncid, nf_global, 'gate_data_truncated', &
                            merge(1, 0, source_nbins > nbins_out))
    call nc_check(nf_enddef(ncid), 'end output definition')

    call nc_check(nf_put_var_real(ncid, z_vd, DBZ), 'write Z')
    call nc_check(nf_put_var_real(ncid, v_vd, VEL), 'write V')
    call nc_check(nf_put_var_real(ncid, w_vd, WID), 'write W')
    scalar_int(1) = sweep_number
    call nc_check(nf_put_var_int(ncid, en_vd, scalar_int), 'write elevationNumber')
    call nc_check(nf_put_var_real(ncid, ea_vd, radialElev(sweep_number)), &
                  'write elevationAngle')
    scalar_int(1) = nrays_out
    call nc_check(nf_put_var_int(ncid, nr_vd, scalar_int), 'write numRadials')
    call nc_check(nf_put_var_real(ncid, ra_vd, Azim), 'write radialAzim')
    call nc_check(nf_put_var_real(ncid, re_vd, elev), 'write radialElev')
    call nc_check(nf_put_var_double(ncid, rt_vd, rtim), 'write radialTime')
    site_name_text = ' '
    site_name_text(1:min(len_trim(RDRNAME), siteNameLen)) = &
      RDRNAME(1:min(len_trim(RDRNAME), siteNameLen))
    radar_name_text = ' '
    radar_name_text(1:min(len_trim(RDRNAME), radarNamelen)) = &
      RDRNAME(1:min(len_trim(RDRNAME), radarNamelen))
    call nc_check(nf_put_var_text(ncid, sn_vd, site_name_text), 'write siteName')
    call nc_check(nf_put_var_text(ncid, rn_vd, radar_name_text), 'write radarName')
    call nc_check(nf_put_var_real(ncid, sla_vd, siteLat), 'write siteLat')
    call nc_check(nf_put_var_real(ncid, slo_vd, siteLon), 'write siteLon')
    call nc_check(nf_put_var_real(ncid, slt_vd, siteAlt), 'write siteAlt')
    scalar_int(1) = 32
    call nc_check(nf_put_var_int(ncid, vc_vd, scalar_int), 'write VCP')
    call nc_check(nf_put_var_double(ncid, es_vd, rtim(1)), 'write esStartTime')
    call nc_check(nf_put_var_double(ncid, ee_vd, rtim(nrays_out)), 'write esEndTime')
    scalar_real(1) = range_km
    call nc_check(nf_put_var_real(ncid, un_vd, scalar_real), 'write unambigRange')
    scalar_real(1) = first_gate_range
    call nc_check(nf_put_var_real(ncid, uz_vd, scalar_real), 'write firstGateRangeZ')
    call nc_check(nf_put_var_real(ncid, uv_vd, scalar_real), 'write firstGateRangeV')
    scalar_real(1) = gate_spacing
    call nc_check(nf_put_var_real(ncid, gsz_vd, scalar_real), 'write gateSizeZ')
    call nc_check(nf_put_var_real(ncid, gsv_vd, scalar_real), 'write gateSizeV')
    scalar_int(1) = nbins_out
    call nc_check(nf_put_var_int(ncid, ngz_vd, scalar_int), 'write numGatesZ')
    call nc_check(nf_put_var_int(ncid, ngv_vd, scalar_int), 'write numGatesV')
    scalar_real(1) = 0.0
    call nc_check(nf_put_var_real(ncid, res_vd, scalar_real), 'write resolutionV')
    call nc_check(nf_put_var_real(ncid, nyq_vd, nyq_vel(sweep_number)), &
                  'write nyquist')
    scalar_real(1) = 0.0
    call nc_check(nf_put_var_real(ncid, cal_vd, scalar_real), 'write calibConst')
    scalar_real(1) = 1.0
    call nc_check(nf_put_var_real(ncid, aaf_vd, scalar_real), 'write atmosAttenFactor')
    scalar_real(1) = 999.0
    call nc_check(nf_put_var_real(ncid, pow_vd, scalar_real), 'write powDiffThreshold')
    call nc_check(nf_close(ncid), 'close output temporary')
    call publish_noreplace(trim(temporary_path), trim(path))
  end subroutine write_sweep

  subroutine publish_noreplace(temporary_path, final_path)
    character(len=*), intent(in) :: temporary_path, final_path
    character(kind=c_char), allocatable :: old_c(:), new_c(:)
    integer(c_int) :: status
    integer :: i

    interface
      function c_link(old_path, new_path) bind(C, name='link') result(result_code)
        import c_char, c_int
        character(kind=c_char), intent(in) :: old_path(*), new_path(*)
        integer(c_int) :: result_code
      end function c_link
      function c_unlink(path) bind(C, name='unlink') result(result_code)
        import c_char, c_int
        character(kind=c_char), intent(in) :: path(*)
        integer(c_int) :: result_code
      end function c_unlink
    end interface

    allocate(old_c(len_trim(temporary_path) + 1))
    allocate(new_c(len_trim(final_path) + 1))
    do i = 1, len_trim(temporary_path)
      old_c(i) = temporary_path(i:i)
    end do
    old_c(len_trim(temporary_path) + 1) = c_null_char
    do i = 1, len_trim(final_path)
      new_c(i) = final_path(i:i)
    end do
    new_c(len_trim(final_path) + 1) = c_null_char

    status = c_link(old_c, new_c)
    if (status /= 0_c_int) then
      call reject('atomic no-replace output publication failed')
    end if
    status = c_unlink(old_c)
    if (status /= 0_c_int) then
      call reject('temporary output cleanup failed after publication')
    end if
    deallocate(old_c, new_c)
  end subroutine publish_noreplace

  subroutine read_time_contract(file_id, time_var_id, time_epoch, time_units, &
                                time_calendar, coverage_start, coverage_end, &
                                coverage_start_epoch, coverage_end_epoch)
    integer, intent(in) :: file_id, time_var_id
    double precision, intent(out) :: time_epoch, coverage_start_epoch, coverage_end_epoch
    character(len=*), intent(out) :: time_units, time_calendar
    character(len=*), intent(out) :: coverage_start, coverage_end

    call read_text_attribute(file_id, time_var_id, 'units', time_units, 'time')
    call optional_text_attribute(file_id, time_var_id, 'calendar', time_calendar, 'time')
    call validate_time_calendar(time_calendar)
    call parse_cf_seconds_since(time_units, time_epoch)
    call read_text_attribute(file_id, nf_global, 'time_coverage_start', &
                             coverage_start, 'global time_coverage_start')
    call read_text_attribute(file_id, nf_global, 'time_coverage_end', &
                             coverage_end, 'global time_coverage_end')
    call parse_iso8601(coverage_start, coverage_start_epoch)
    call parse_iso8601(coverage_end, coverage_end_epoch)
    if (coverage_end_epoch < coverage_start_epoch) then
      call reject('time coverage end precedes time coverage start')
    end if
  end subroutine read_time_contract

  subroutine parse_cf_seconds_since(units, epoch)
    character(len=*), intent(in) :: units
    double precision, intent(out) :: epoch
    character(len=255) :: value

    value = adjustl(units)
    if (len_trim(value) < 15 .or. value(1:14) /= 'seconds since ') then
      call reject('time units must be CF seconds since an explicit UTC origin')
    end if
    call parse_iso8601(value(15:), epoch)
  end subroutine parse_cf_seconds_since

  subroutine parse_iso8601(value, epoch)
    character(len=*), intent(in) :: value
    double precision, intent(out) :: epoch
    character(len=255) :: text, second_text
    integer :: year, month, day, hour, minute, ios, n
    double precision :: second
    integer(kind=8) :: julian_day, epoch_day, base_day

    text = adjustl(value)
    n = len_trim(text)
    if (n < 20 .or. n > len(text) .or. text(5:5) /= '-' .or. &
        text(8:8) /= '-' .or. text(11:11) /= 'T' .or. text(14:14) /= ':' .or. &
        text(17:17) /= ':' .or. text(n:n) /= 'Z') then
      call reject('time origin or coverage is not an explicit UTC ISO-8601 value')
    end if
    read(text(1:4), *, iostat=ios) year
    if (ios /= 0) call reject('time origin year is invalid')
    read(text(6:7), *, iostat=ios) month
    if (ios /= 0) call reject('time origin month is invalid')
    read(text(9:10), *, iostat=ios) day
    if (ios /= 0) call reject('time origin day is invalid')
    read(text(12:13), *, iostat=ios) hour
    if (ios /= 0) call reject('time origin hour is invalid')
    read(text(15:16), *, iostat=ios) minute
    if (ios /= 0) call reject('time origin minute is invalid')
    second_text = text(18:n-1)
    read(second_text, *, iostat=ios) second
    if (ios /= 0) call reject('time origin seconds are invalid')
    if (year < 1970 .or. month < 1 .or. month > 12 .or. day < 1 .or. &
        day > days_in_month(year, month) .or. hour < 0 .or. hour > 23 .or. &
        minute < 0 .or. minute > 59 .or. second < 0.0d0 .or. second >= 60.0d0) then
      call reject('time origin is outside the supported UTC Gregorian range')
    end if
    julian_day = int(day, 8) + int((153 * (month + 12 * ((14 - month) / 12) - 3) + 2) / 5, 8) + &
                 365_8 * int(year + 4800 - (14 - month) / 12, 8) + &
                 int((year + 4800 - (14 - month) / 12) / 4, 8) - &
                 int((year + 4800 - (14 - month) / 12) / 100, 8) + &
                 int((year + 4800 - (14 - month) / 12) / 400, 8) - 32045_8
    base_day = 2440588_8
    epoch_day = julian_day - base_day
    epoch = dble(epoch_day * 86400_8) + dble(hour * 3600 + minute * 60) + second
  end subroutine parse_iso8601

  integer function days_in_month(year, month)
    integer, intent(in) :: year, month
    integer, dimension(12) :: month_days
    month_days = (/31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31/)
    days_in_month = month_days(month)
    if (month == 2 .and. (mod(year, 400) == 0 .or. &
        (mod(year, 4) == 0 .and. mod(year, 100) /= 0))) then
      days_in_month = 29
    end if
  end function days_in_month

  subroutine validate_time_calendar(calendar)
    character(len=*), intent(in) :: calendar
    character(len=64) :: value
    value = adjustl(calendar)
    if (trim(value) /= 'standard' .and. trim(value) /= 'gregorian' .and. &
        trim(value) /= 'proleptic_gregorian') then
      call reject('unsupported CF time calendar')
    end if
  end subroutine validate_time_calendar

  subroutine validate_juldate(juldate, origin_text)
    character(len=*), intent(in) :: juldate, origin_text
    character(len=255) :: text
    character(len=9) :: expected
    integer :: year, month, day, hour, minute, ios, day_of_year, m

    text = adjustl(origin_text)
    read(text(1:4), *, iostat=ios) year
    if (ios /= 0) call reject('time origin year is invalid')
    read(text(6:7), *, iostat=ios) month
    if (ios /= 0) call reject('time origin month is invalid')
    read(text(9:10), *, iostat=ios) day
    if (ios /= 0) call reject('time origin day is invalid')
    read(text(12:13), *, iostat=ios) hour
    if (ios /= 0) call reject('time origin hour is invalid')
    read(text(15:16), *, iostat=ios) minute
    if (ios /= 0) call reject('time origin minute is invalid')
    day_of_year = day
    do m = 1, month - 1
      day_of_year = day_of_year + days_in_month(year, m)
    end do
    write(expected, '(I2.2,I3.3,I2.2,I2.2)') mod(year, 100), day_of_year, hour, minute
    if (trim(juldate) /= trim(expected)) then
      call reject('JULDATE does not match the CF time origin')
    end if
  end subroutine validate_juldate

  subroutine read_dimension(file_id, name, dim_id, length)
    integer, intent(in) :: file_id
    character(len=*), intent(in) :: name
    integer, intent(out) :: dim_id, length
    call nc_check(nf_inq_dimid(file_id, trim(name), dim_id), &
                  'find dimension '//trim(name))
    call nc_check(nf_inq_dimlen(file_id, dim_id, length), &
                  'read dimension '//trim(name))
  end subroutine read_dimension

  subroutine require_1d_var(file_id, name, expected_dim, expected_len, expected_type, var_id)
    integer, intent(in) :: file_id, expected_dim, expected_len, expected_type
    character(len=*), intent(in) :: name
    integer, intent(out) :: var_id
    integer :: rank, dimensions(nf_max_var_dims), var_type, actual_len
    call nc_check(nf_inq_varid(file_id, trim(name), var_id), &
                  'find variable '//trim(name))
    call nc_check(nf_inq_varndims(file_id, var_id, rank), &
                  'read rank '//trim(name))
    if (rank /= 1) call reject(trim(name)//' must be one dimensional')
    call nc_check(nf_inq_vardimid(file_id, var_id, dimensions), &
                  'read dimensions '//trim(name))
    if (dimensions(1) /= expected_dim) then
      call reject(trim(name)//' uses an unexpected dimension')
    end if
    call nc_check(nf_inq_dimlen(file_id, expected_dim, actual_len), &
                  'read length for '//trim(name))
    if (actual_len /= expected_len) call reject(trim(name)//' has unexpected length')
    call nc_check(nf_inq_vartype(file_id, var_id, var_type), &
                  'read type '//trim(name))
    if (var_type /= expected_type) call reject(trim(name)//' has an unexpected type')
  end subroutine require_1d_var

  subroutine require_scalar_var(file_id, name, var_id)
    integer, intent(in) :: file_id
    character(len=*), intent(in) :: name
    integer, intent(out) :: var_id
    integer :: rank
    call nc_check(nf_inq_varid(file_id, trim(name), var_id), &
                  'find variable '//trim(name))
    call nc_check(nf_inq_varndims(file_id, var_id, rank), &
                  'read rank '//trim(name))
    if (rank /= 0) call reject(trim(name)//' must be scalar')
  end subroutine require_scalar_var

  subroutine required_real_attribute(file_id, var_id, name, value, variable)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name, variable
    real, intent(out) :: value
    call nc_check(nf_get_att_real(file_id, var_id, trim(name), value), &
                  'read '//trim(variable)//' '//trim(name))
    if (.not.ieee_is_finite(value)) call reject(trim(variable)//' '//trim(name)//' is nonfinite')
  end subroutine required_real_attribute

  subroutine optional_real_attribute(file_id, var_id, name, value, variable)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name, variable
    real, intent(out) :: value
    integer :: status
    value = 0.0
    status = nf_get_att_real(file_id, var_id, trim(name), value)
    if (status /= nf_noerr .and. status /= nf_enotatt) then
      call nc_check(status, 'read '//trim(variable)//' '//trim(name))
    end if
    if (.not.ieee_is_finite(value)) call reject(trim(variable)//' '//trim(name)//' is nonfinite')
  end subroutine optional_real_attribute

  subroutine require_text_attribute(file_id, var_id, name, expected, variable)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name, expected, variable
    character(len=64) :: value
    integer :: length
    call nc_check(nf_inq_attlen(file_id, var_id, trim(name), length), &
                  'read length '//trim(variable)//' '//trim(name))
    if (length /= len_trim(expected)) call reject(trim(variable)//' units length mismatch')
    value = ' '
    call nc_check(nf_get_att_text(file_id, var_id, trim(name), value), &
                  'read text '//trim(variable)//' '//trim(name))
    if (trim(value) /= trim(expected)) call reject(trim(variable)//' has unexpected '//trim(name))
  end subroutine require_text_attribute

  subroutine read_text_attribute(file_id, var_id, name, value, variable)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name, variable
    character(len=*), intent(out) :: value
    integer :: length
    call nc_check(nf_inq_attlen(file_id, var_id, trim(name), length), &
                  'read length '//trim(variable)//' '//trim(name))
    if (length <= 0 .or. length > len(value)) then
      call reject(trim(variable)//' '//trim(name)//' length is outside the supported range')
    end if
    value = ' '
    call nc_check(nf_get_att_text(file_id, var_id, trim(name), value), &
                  'read text '//trim(variable)//' '//trim(name))
    if (len_trim(value) == 0) call reject(trim(variable)//' has an empty '//trim(name))
  end subroutine read_text_attribute

  subroutine optional_text_attribute(file_id, var_id, name, value, variable)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name, variable
    character(len=*), intent(out) :: value
    integer :: length, status
    status = nf_inq_attlen(file_id, var_id, trim(name), length)
    if (status == nf_enotatt) then
      value = 'standard'
      return
    end if
    call nc_check(status, 'read length '//trim(variable)//' '//trim(name))
    if (length <= 0 .or. length > len(value)) then
      call reject(trim(variable)//' '//trim(name)//' length is outside the supported range')
    end if
    value = ' '
    call nc_check(nf_get_att_text(file_id, var_id, trim(name), value), &
                  'read text '//trim(variable)//' '//trim(name))
    if (len_trim(value) == 0) call reject(trim(variable)//' has an empty '//trim(name))
  end subroutine optional_text_attribute

  subroutine require_finite_real(values, name)
    real, intent(in) :: values(:)
    character(len=*), intent(in) :: name
    if (any(.not.ieee_is_finite(values))) call reject(trim(name)//' contains nonfinite values')
  end subroutine require_finite_real

  subroutine require_finite_double(values, name)
    double precision, intent(in) :: values(:)
    character(len=*), intent(in) :: name
    if (any(.not.ieee_is_finite(values))) call reject(trim(name)//' contains nonfinite values')
  end subroutine require_finite_double

  subroutine require_positive_scale(value, name)
    real, intent(in) :: value
    character(len=*), intent(in) :: name
    if (.not.ieee_is_finite(value) .or. value <= 0.0) call reject(trim(name)//' must be positive')
  end subroutine require_positive_scale

  subroutine set_packed_range(scale, offset, values)
    real, intent(in) :: scale, offset
    real, allocatable, intent(out) :: values(:)
    real :: low, high
    allocate(values(2))
    low = -32767.0 * scale + offset
    high = 32767.0 * scale + offset
    values = (/min(low, high), max(low, high)/)
  end subroutine set_packed_range

  subroutine put_text_att(file_id, var_id, name, value)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name, value
    call nc_check(nf_put_att_text(file_id, var_id, trim(name), len_trim(value), trim(value)), &
                  'write attribute '//trim(name))
  end subroutine put_text_att

  subroutine put_real_att(file_id, var_id, name, values)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name
    real, intent(in) :: values(:)
    call nc_check(nf_put_att_real(file_id, var_id, trim(name), nf_real, size(values), values), &
                  'write attribute '//trim(name))
  end subroutine put_real_att

  subroutine put_real_scalar_att(file_id, var_id, name, value)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name
    real, intent(in) :: value
    real :: values(1)
    values(1) = value
    call put_real_att(file_id, var_id, name, values)
  end subroutine put_real_scalar_att

  subroutine put_int_att(file_id, var_id, name, values)
    integer, intent(in) :: file_id, var_id
    character(len=*), intent(in) :: name
    integer, intent(in) :: values(:)
    call nc_check(nf_put_att_int(file_id, var_id, trim(name), nf_int, size(values), values), &
                  'write attribute '//trim(name))
  end subroutine put_int_att

  subroutine put_int_scalar_att(file_id, var_id, name, value)
    integer, intent(in) :: file_id, var_id, value
    character(len=*), intent(in) :: name
    integer :: values(1)
    values(1) = value
    call nc_check(nf_put_att_int(file_id, var_id, trim(name), nf_int, 1, values), &
                  'write attribute '//trim(name))
  end subroutine put_int_scalar_att

  subroutine required_environment(name, value)
    character(len=*), intent(in) :: name
    character(len=*), intent(out) :: value
    integer :: status
    value = ' '
    call get_environment_variable(trim(name), value, status=status)
    if (status /= 0 .or. len_trim(value) == 0) then
      call reject('required environment variable is missing: '//trim(name))
    end if
  end subroutine required_environment

  subroutine required_argument(index, value, description)
    integer, intent(in) :: index
    character(len=*), intent(out) :: value
    character(len=*), intent(in) :: description
    integer :: length, status
    value = ' '
    call get_command_argument(index, value, length=length, status=status)
    if (status /= 0 .or. length == 0) call reject('required '//trim(description)//' is missing')
  end subroutine required_argument

  subroutine nc_check(status, context)
    integer, intent(in) :: status
    character(len=*), intent(in) :: context
    if (status /= nf_noerr) then
      write(*, '(A,A,A,I0)') 'DECODER_NETCDF_ERROR ', trim(context), ' status=', status
      error stop 2
    end if
  end subroutine nc_check

  subroutine reject(message)
    character(len=*), intent(in) :: message
    write(*, '(A,A)') 'DECODER_REJECTED: ', trim(message)
    error stop 2
  end subroutine reject

end program RDR_PREP_EXPRESS
