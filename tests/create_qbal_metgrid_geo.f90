PROGRAM create_qbal_metgrid_geo
  ! Create the smallest C-grid geogrid file needed by the qbal metgrid
  ! fixture.  Coordinates are evaluated with the pinned WPS map_utils
  ! implementation; no latitude/longitude approximation is used here.
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32
  USE netcdf
  USE map_utils, ONLY: ij_to_latlon, map_set, proj_info
  USE misc_definitions_module, ONLY: PROJ_LC
  IMPLICIT NONE

  INTEGER, PARAMETER :: nx = 4, ny = 4, nx_stag = 5, ny_stag = 5
  INTEGER, PARAMETER :: ntime = 1, date_len = 19
  REAL(real32), PARAMETER :: dx = 10000.0_real32
  ! The target uses the WPS/WRF sphere; the approved source uses 6371229 m.
  REAL(real32), PARAMETER :: earth_radius = 6370000.0_real32
  REAL(real32), PARAMETER :: lat_origin = 45.0_real32
  REAL(real32), PARAMETER :: lon_origin = 127.0_real32
  REAL(real32), PARAMETER :: stdlon = 127.0_real32
  REAL(real32), PARAMETER :: truelat = 45.0_real32
  REAL(real32), PARAMETER :: mass_origin = 2.2_real32
  REAL(real32), PARAMETER :: stagger_origin = 1.7_real32
  CHARACTER(LEN=1024) :: output_path
  TYPE(proj_info) :: target_projection
  REAL(real32) :: xlat_m(nx,ny,ntime), xlon_m(nx,ny,ntime)
  REAL(real32) :: xlat_u(nx_stag,ny,ntime), xlon_u(nx_stag,ny,ntime)
  REAL(real32) :: xlat_v(nx,ny_stag,ntime), xlon_v(nx,ny_stag,ntime)
  REAL(real32) :: landmask(nx,ny,ntime), hgt_m(nx,ny,ntime)
  REAL(real32) :: corner_lats(16), corner_lons(16), cen_lat, cen_lon
  CHARACTER(LEN=date_len) :: times(ntime)
  INTEGER :: ncid, time_dim, date_dim, we_dim, sn_dim
  INTEGER :: we_stag_dim, sn_stag_dim, varid
  INTEGER :: dims_mass(3), dims_u(3), dims_v(3), dims_times(2)

  IF (COMMAND_ARGUMENT_COUNT() /= 1) ERROR STOP &
       'usage: create_qbal_metgrid_geo output_geo_em.nc'
  CALL GET_COMMAND_ARGUMENT(1, output_path)

  CALL map_set(PROJ_LC, target_projection, lat1=lat_origin, lon1=lon_origin, &
       knowni=1.0_real32, knownj=1.0_real32, dx=dx, dy=dx, stdlon=stdlon, &
       truelat1=truelat, truelat2=truelat, r_earth=earth_radius)
  CALL fill_coordinates(target_projection, xlat_m, xlon_m, xlat_u, xlon_u, &
       xlat_v, xlon_v, corner_lats, corner_lons, cen_lat, cen_lon)
  landmask = 1.0_real32
  hgt_m = 0.0_real32
  ! Static geogrid fields use the timeless WRF I/O lookup key.
  times(1) = '0000-00-00_00:00:00'

  CALL check(nf90_create(TRIM(output_path), NF90_CLOBBER, ncid), &
       'create geogrid file')
  CALL check(nf90_def_dim(ncid, 'Time', ntime, time_dim), 'define Time')
  CALL check(nf90_def_dim(ncid, 'DateStrLen', date_len, date_dim), &
       'define DateStrLen')
  CALL check(nf90_def_dim(ncid, 'west_east', nx, we_dim), 'define west_east')
  CALL check(nf90_def_dim(ncid, 'south_north', ny, sn_dim), 'define south_north')
  CALL check(nf90_def_dim(ncid, 'west_east_stag', nx_stag, we_stag_dim), &
       'define west_east_stag')
  CALL check(nf90_def_dim(ncid, 'south_north_stag', ny_stag, sn_stag_dim), &
       'define south_north_stag')

  dims_mass = [we_dim, sn_dim, time_dim]
  dims_u = [we_stag_dim, sn_dim, time_dim]
  dims_v = [we_dim, sn_stag_dim, time_dim]
  dims_times = [date_dim, time_dim]
  CALL check(nf90_def_var(ncid, 'Times', NF90_CHAR, dims_times, varid), &
       'define Times')
  CALL define_field(ncid, 'XLAT_M', dims_mass, 'degrees latitude', &
       'Latitude on mass grid', 'M', varid)
  CALL define_field(ncid, 'XLONG_M', dims_mass, 'degrees longitude', &
       'Longitude on mass grid', 'M', varid)
  CALL define_field(ncid, 'XLAT_U', dims_u, 'degrees latitude', &
       'Latitude on U grid', 'U', varid)
  CALL define_field(ncid, 'XLONG_U', dims_u, 'degrees longitude', &
       'Longitude on U grid', 'U', varid)
  CALL define_field(ncid, 'XLAT_V', dims_v, 'degrees latitude', &
       'Latitude on V grid', 'V', varid)
  CALL define_field(ncid, 'XLONG_V', dims_v, 'degrees longitude', &
       'Longitude on V grid', 'V', varid)
  CALL define_field(ncid, 'LANDMASK', dims_mass, '1=land, 0=water', &
       'Land mask', 'M', varid)
  CALL define_field(ncid, 'HGT_M', dims_mass, 'm', &
       'Topography height', 'M', varid)

  CALL put_global_attributes(ncid, cen_lat, cen_lon, corner_lats, corner_lons)
  CALL check(nf90_enddef(ncid), 'end geogrid definition')

  CALL check(nf90_inq_varid(ncid, 'Times', varid), 'find Times')
  CALL check(nf90_put_var(ncid, varid, times), 'write Times')
  CALL put_field(ncid, 'XLAT_M', xlat_m)
  CALL put_field(ncid, 'XLONG_M', xlon_m)
  CALL put_field(ncid, 'XLAT_U', xlat_u)
  CALL put_field(ncid, 'XLONG_U', xlon_u)
  CALL put_field(ncid, 'XLAT_V', xlat_v)
  CALL put_field(ncid, 'XLONG_V', xlon_v)
  CALL put_field(ncid, 'LANDMASK', landmask)
  CALL put_field(ncid, 'HGT_M', hgt_m)
  CALL check(nf90_close(ncid), 'close geogrid file')
  WRITE(*,'(A)') 'WROTE_QBAL_GEOGRID='//TRIM(output_path)

CONTAINS

  SUBROUTINE check(rc, operation)
    INTEGER, INTENT(IN) :: rc
    CHARACTER(*), INTENT(IN) :: operation
    IF (rc /= NF90_NOERR) ERROR STOP TRIM(operation)//': '//TRIM(nf90_strerror(rc))
  END SUBROUTINE check

  SUBROUTINE point(projection, i_coord, j_coord, lat, lon)
    TYPE(proj_info), INTENT(IN) :: projection
    REAL(real32), INTENT(IN) :: i_coord, j_coord
    REAL(real32), INTENT(OUT) :: lat, lon
    CALL ij_to_latlon(projection, i_coord, j_coord, lat, lon)
  END SUBROUTINE point

  SUBROUTINE fill_coordinates(projection, lat_m, lon_m, lat_u, lon_u, &
                              lat_v, lon_v, corners_lat, corners_lon, &
                              center_lat, center_lon)
    TYPE(proj_info), INTENT(IN) :: projection
    REAL(real32), INTENT(OUT) :: lat_m(nx,ny,ntime), lon_m(nx,ny,ntime)
    REAL(real32), INTENT(OUT) :: lat_u(nx_stag,ny,ntime), lon_u(nx_stag,ny,ntime)
    REAL(real32), INTENT(OUT) :: lat_v(nx,ny_stag,ntime), lon_v(nx,ny_stag,ntime)
    REAL(real32), INTENT(OUT) :: corners_lat(16), corners_lon(16)
    REAL(real32), INTENT(OUT) :: center_lat, center_lon
    INTEGER :: i, j

    DO j = 1, ny
      DO i = 1, nx
        CALL point(projection, mass_origin+REAL(i-1,real32), &
             mass_origin+REAL(j-1,real32), lat_m(i,j,1), lon_m(i,j,1))
      END DO
    END DO
    DO j = 1, ny
      DO i = 1, nx_stag
        CALL point(projection, stagger_origin+REAL(i-1,real32), &
             mass_origin+REAL(j-1,real32), lat_u(i,j,1), lon_u(i,j,1))
      END DO
    END DO
    DO j = 1, ny_stag
      DO i = 1, nx
        CALL point(projection, mass_origin+REAL(i-1,real32), &
             stagger_origin+REAL(j-1,real32), lat_v(i,j,1), lon_v(i,j,1))
      END DO
    END DO

    CALL point(projection, mass_origin, mass_origin, corners_lat(1), corners_lon(1))
    CALL point(projection, mass_origin, mass_origin+3.0_real32, corners_lat(2), corners_lon(2))
    CALL point(projection, mass_origin+3.0_real32, mass_origin+3.0_real32, corners_lat(3), corners_lon(3))
    CALL point(projection, mass_origin+3.0_real32, mass_origin, corners_lat(4), corners_lon(4))
    CALL point(projection, stagger_origin, mass_origin, corners_lat(5), corners_lon(5))
    CALL point(projection, stagger_origin, mass_origin+3.0_real32, corners_lat(6), corners_lon(6))
    CALL point(projection, stagger_origin+4.0_real32, mass_origin+3.0_real32, corners_lat(7), corners_lon(7))
    CALL point(projection, stagger_origin+4.0_real32, mass_origin, corners_lat(8), corners_lon(8))
    CALL point(projection, mass_origin, stagger_origin, corners_lat(9), corners_lon(9))
    CALL point(projection, mass_origin, stagger_origin+4.0_real32, corners_lat(10), corners_lon(10))
    CALL point(projection, mass_origin+3.0_real32, stagger_origin+4.0_real32, corners_lat(11), corners_lon(11))
    CALL point(projection, mass_origin+3.0_real32, stagger_origin, corners_lat(12), corners_lon(12))
    CALL point(projection, stagger_origin, stagger_origin, corners_lat(13), corners_lon(13))
    CALL point(projection, stagger_origin, stagger_origin+4.0_real32, corners_lat(14), corners_lon(14))
    CALL point(projection, stagger_origin+4.0_real32, stagger_origin+4.0_real32, corners_lat(15), corners_lon(15))
    CALL point(projection, stagger_origin+4.0_real32, stagger_origin, corners_lat(16), corners_lon(16))
    CALL point(projection, mass_origin+1.5_real32, mass_origin+1.5_real32, center_lat, center_lon)
  END SUBROUTINE fill_coordinates

  SUBROUTINE define_field(file_id, name, dimensions, units, description, stagger, id)
    INTEGER, INTENT(IN) :: file_id, dimensions(:)
    CHARACTER(*), INTENT(IN) :: name, units, description, stagger
    INTEGER, INTENT(OUT) :: id
    CALL check(nf90_def_var(file_id, TRIM(name), NF90_FLOAT, dimensions, id), &
         'define '//TRIM(name))
    CALL check(nf90_put_att(file_id, id, 'units', TRIM(units)), &
         'set units '//TRIM(name))
    CALL check(nf90_put_att(file_id, id, 'description', TRIM(description)), &
         'set description '//TRIM(name))
    CALL check(nf90_put_att(file_id, id, 'stagger', TRIM(stagger)), &
         'set stagger '//TRIM(name))
    CALL check(nf90_put_att(file_id, id, 'MemoryOrder', 'XY '), &
         'set MemoryOrder '//TRIM(name))
    CALL check(nf90_put_att(file_id, id, 'FieldType', 104), &
         'set FieldType '//TRIM(name))
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'FLAG_'//TRIM(name), 1), 'set field flag')
    CALL check(nf90_put_att(file_id, id, 'sr_x', 1), 'set sr_x '//TRIM(name))
    CALL check(nf90_put_att(file_id, id, 'sr_y', 1), 'set sr_y '//TRIM(name))
  END SUBROUTINE define_field

  SUBROUTINE put_field(file_id, name, values)
    INTEGER, INTENT(IN) :: file_id
    CHARACTER(*), INTENT(IN) :: name
    REAL(real32), INTENT(IN) :: values(:,:,:)
    INTEGER :: id
    CALL check(nf90_inq_varid(file_id, TRIM(name), id), 'find '//TRIM(name))
    CALL check(nf90_put_var(file_id, id, values), 'write '//TRIM(name))
  END SUBROUTINE put_field

  SUBROUTINE put_global_attributes(file_id, center_lat, center_lon, corners_lat, corners_lon)
    INTEGER, INTENT(IN) :: file_id
    REAL(real32), INTENT(IN) :: center_lat, center_lon
    REAL(real32), INTENT(IN) :: corners_lat(16), corners_lon(16)
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'TITLE', &
         'OUTPUT FROM GEOGRID V4.6.0'), 'set TITLE')
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'SIMULATION_START_DATE', &
         '2023-05-18_03:33:20'), 'set SIMULATION_START_DATE')
    CALL put_int_attribute(file_id, 'WEST-EAST_GRID_DIMENSION', 5)
    CALL put_int_attribute(file_id, 'SOUTH-NORTH_GRID_DIMENSION', 5)
    CALL put_int_attribute(file_id, 'BOTTOM-TOP_GRID_DIMENSION', 1)
    CALL put_int_attribute(file_id, 'WEST-EAST_PATCH_START_UNSTAG', 1)
    CALL put_int_attribute(file_id, 'WEST-EAST_PATCH_END_UNSTAG', 4)
    CALL put_int_attribute(file_id, 'WEST-EAST_PATCH_START_STAG', 1)
    CALL put_int_attribute(file_id, 'WEST-EAST_PATCH_END_STAG', 5)
    CALL put_int_attribute(file_id, 'SOUTH-NORTH_PATCH_START_UNSTAG', 1)
    CALL put_int_attribute(file_id, 'SOUTH-NORTH_PATCH_END_UNSTAG', 4)
    CALL put_int_attribute(file_id, 'SOUTH-NORTH_PATCH_START_STAG', 1)
    CALL put_int_attribute(file_id, 'SOUTH-NORTH_PATCH_END_STAG', 5)
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'GRIDTYPE', 'C'), 'set GRIDTYPE')
    CALL put_real_attribute(file_id, 'DX', dx)
    CALL put_real_attribute(file_id, 'DY', dx)
    CALL put_int_attribute(file_id, 'DYN_OPT', 2)
    CALL put_real_attribute(file_id, 'CEN_LAT', center_lat)
    CALL put_real_attribute(file_id, 'CEN_LON', center_lon)
    CALL put_real_attribute(file_id, 'TRUELAT1', truelat)
    CALL put_real_attribute(file_id, 'TRUELAT2', truelat)
    CALL put_real_attribute(file_id, 'MOAD_CEN_LAT', center_lat)
    CALL put_real_attribute(file_id, 'STAND_LON', stdlon)
    CALL put_real_attribute(file_id, 'POLE_LAT', 90.0_real32)
    CALL put_real_attribute(file_id, 'POLE_LON', 0.0_real32)
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'corner_lats', corners_lat), &
         'set corner_lats')
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'corner_lons', corners_lon), &
         'set corner_lons')
    CALL put_int_attribute(file_id, 'MAP_PROJ', 1)
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, 'MMINLU', &
         'MODIFIED_IGBP_MODIS_NOAH'), 'set MMINLU')
    CALL put_int_attribute(file_id, 'NUM_LAND_CAT', 21)
    CALL put_int_attribute(file_id, 'ISWATER', 16)
    CALL put_int_attribute(file_id, 'ISLAKE', 21)
    CALL put_int_attribute(file_id, 'ISICE', 15)
    CALL put_int_attribute(file_id, 'ISURBAN', 13)
    CALL put_int_attribute(file_id, 'ISOILWATER', 14)
    CALL put_int_attribute(file_id, 'grid_id', 1)
    CALL put_int_attribute(file_id, 'parent_id', 1)
    CALL put_int_attribute(file_id, 'i_parent_start', 1)
    CALL put_int_attribute(file_id, 'j_parent_start', 1)
    CALL put_int_attribute(file_id, 'i_parent_end', 5)
    CALL put_int_attribute(file_id, 'j_parent_end', 5)
    CALL put_int_attribute(file_id, 'parent_grid_ratio', 1)
    CALL put_int_attribute(file_id, 'sr_x', 1)
    CALL put_int_attribute(file_id, 'sr_y', 1)
  END SUBROUTINE put_global_attributes

  SUBROUTINE put_int_attribute(file_id, name, value)
    INTEGER, INTENT(IN) :: file_id, value
    CHARACTER(*), INTENT(IN) :: name
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, TRIM(name), value), &
         'set '//TRIM(name))
  END SUBROUTINE put_int_attribute

  SUBROUTINE put_real_attribute(file_id, name, value)
    INTEGER, INTENT(IN) :: file_id
    CHARACTER(*), INTENT(IN) :: name
    REAL(real32), INTENT(IN) :: value
    CALL check(nf90_put_att(file_id, NF90_GLOBAL, TRIM(name), value), &
         'set '//TRIM(name))
  END SUBROUTINE put_real_attribute
END PROGRAM create_qbal_metgrid_geo
