&lapsprep_nl
 HOTSTART = .true.,
 BALANCE = .true., 
 OUTPUT_FORMAT = 'wps',
 SNOW_THRESH = 1.1,
 LWC2VAPOR_THRESH = 0.00,
 MAKE_SFC_UV = .false.,
 HYDRO_MODE = 'CONSERVATIVE',
 GRID_SCALE = 'NONE',
 CAP_POLICY = 'TRANSFER',
 WIND_COORDINATE = 'GRID_RELATIVE',
 ENFORCE_FIELD_CONTRACTS = .true.,
 
/
c
c  hotstart:
c    Logical flag, set to true to pull in the five hydrometeor species
c    into the output files.  
c
c  balance:
c    Logical flag, set to true to use the balanced wind, temp, height 
c    fields.  Normally set to true if hotstart is true.
c
c  output_format:
c    List of character strings, one specifying each output format to
c    be made per run of lapsprep.  Valid values:
c      'mm5':  Makes files suitable for ingest into regridder
c      'wrf':  Makes files for hinterp ingest
c      'rams':  Makes RALPH2 format
c      'cdf':  Generic netCDF format used by FSL RAMS for hot start.
c
c  snow_thresh:
c    Real value, controls the setting of the snow cover flag in the output.
c    Any value of snow cover fraction from the LAPS analysis (0.->1.0) 
c    exceeding this threshold will cause the snow cover flag to be set
c    in the output.  To prevent any snow cover flags from being set, set
c    this value > 1.0.
c
c  lwc2vapor_thresh:
c    Real value, controls the conversion of cloud liquid to vapor.  Set
c    to 0 to disable.  If enabled, typical values are going to be around
c    1.0 (default value is 1.1).  If set to 1.0, cloud water will be converted
c    to vapor up until the RH for that point reaches 100%.  Any remaining 
c    cloud water will be left in place.  Values greater than 1.0 allow
c    for supersaturation (e.g., 1.1 allows 110% max RH).
c
c  make_sfc_uv:
c    Logical flag. If set to true, then the surface u/v fields from lsx
c    will be replaced with winds interpolated from the 3D isobaric 
c    u/v fields.
c
c  Cloud-BAL controls:
c    LWC2VAPOR_THRESH remains zero until the canonical water/enthalpy
c    adjustment is linked; the legacy water-only transfer is not authorized.
c    HYDRO_MODE='CONSERVATIVE' preserves dry-air hydrometeor mass basis.
c    GRID_SCALE='NONE' removes the undocumented 2/dx concentration scaling.
c    CAP_POLICY='TRANSFER' moves cap excess into rain/snow instead of dropping it.
c    WIND_COORDINATE is mandatory WPS metadata: GRID_RELATIVE or EARTH_RELATIVE.
c    Radar authority is not owned by LAPSPREP.  The single Cloud-BAL pipeline
c    mode defaults to SHADOW; the dormant evaporation path remains unavailable.
c    ENFORCE_FIELD_CONTRACTS keeps cell validity separate from physical zero.
c    Any value of snow cover fraction from the LAPS analysis (0.->1.0) 
c    1.0 (default value is 1.1).  If set to 1.0, cloud water will be converted
c    for supersaturation (e.g., 1.1 allows 110% max RH).
c    Logical flag. If set to true, then the surface u/v fields from lsx
c    u/v fields.
