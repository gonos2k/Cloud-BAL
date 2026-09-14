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

      subroutine get_tilt_netcdf_data(filename
     1                               ,radarName
     1                               ,siteLat                        
     1                               ,siteLon                        
     1                               ,siteAlt                        
     1                               ,elevationAngle
     1                               ,numRadials 
     1                               ,numGatesV
     1                               ,numGatesZ
     1                               ,elevationNumber
     1                               ,VCP
     1                               ,nyquist
     1                               ,radialAzim
     1                               ,Z  
     1                               ,V
     1                               ,resolutionV
     1                               ,gateSizeV,gateSizeZ
     1                               ,firstGateRangeV,firstGateRangeZ
     1                               ,V_bin_max, Z_bin_max, radial_max
     1                               ,istatus)

!     Argument List
      implicit none
      character*(*) filename
      character*5  radarName
      integer V_bin_max, Z_bin_max, radial_max
      real V(V_bin_max,radial_max), Z(Z_bin_max,radial_max)  !!! kys
ckys  integer V(V_bin_max,radial_max), Z(Z_bin_max,radial_max)
      real radialAzim(radial_max)
      real siteLat,siteLon,siteAlt,elevationAngle,nyquist
      real resolutionV,gateSizeV,gateSizeZ
      real firstGateRangeV,firstGateRangeZ
      integer numRadials,elevationNumber,VCP,numGatesV,numGatesZ,istatus

!     Local
      real radialElev(radial_max)
      real atmosAttenFactor,calibConst,powDiffThreshold
      real unambigRange
      character*132 siteName
      double precision esEndTime, esStartTime, radialTime(radial_max)

!.............................................................................

      include 'netcdf.inc'
      integer V_bin, Z_bin, radial,nf_fid, nf_vid, nf_status
      integer schema_status, i

      istatus = 0

!     include 'remap_constants.dat' ! for debugging only
!     include 'remap.cmn' ! for debugging only

      write(6,*)' get_tilt_netcdf_data: reading ',filename
C
C  Open netcdf File for reading
C
      nf_status = NF_OPEN(filename,NF_NOWRITE,nf_fid)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'NF_OPEN ',filename
        istatus = 0
        return
      endif
C
C  Fill all dimension values
C
C
C Get size of V_bin
C
      nf_status = NF_INQ_DIMID(nf_fid,'V_bin',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'dim V_bin'
        nf_status = nf_close(nf_fid)
        return
      endif
      nf_status = NF_INQ_DIMLEN(nf_fid,nf_vid,V_bin)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'dim V_bin'
        nf_status = nf_close(nf_fid)
        return
      endif
C
C Get size of Z_bin
C
      nf_status = NF_INQ_DIMID(nf_fid,'Z_bin',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'dim Z_bin'
        nf_status = nf_close(nf_fid)
        return
      endif
      nf_status = NF_INQ_DIMLEN(nf_fid,nf_vid,Z_bin)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'dim Z_bin'
        nf_status = nf_close(nf_fid)
        return
      endif
C
C Get size of radial
C
      nf_status = NF_INQ_DIMID(nf_fid,'radial',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'dim radial'
        nf_status = nf_close(nf_fid)
        return
      endif
      nf_status = NF_INQ_DIMLEN(nf_fid,nf_vid,radial)
      if(nf_status.ne.NF_NOERR) then
        print *, NF_STRERROR(nf_status)
        print *,'dim radial'
        nf_status = nf_close(nf_fid)
        return
      endif

!.....Test whether dimensions of NetCDF file are within bounds...............

      if(V_bin .ne. V_bin_max)then
          write(6,*)' V_bin != permitted dimensions ',V_bin,V_bin_max
          nf_status = nf_close(nf_fid)
          return
      endif

      if(Z_bin .ne. Z_bin_max)then
          write(6,*)' Z_bin != permitted dimensions ',Z_bin,Z_bin_max
          nf_status = nf_close(nf_fid)
          return
      endif

      if(radial .lt. 1 .or. radial .gt. radial_max)then
          write(6,*)' radial outside permitted dimensions ',radial,
     +        radial_max
          nf_status = nf_close(nf_fid)
          return
      endif

      call validate_radar_schema(nf_fid,V_bin,Z_bin,radial,
     + schema_status)
      if(schema_status .ne. 1)then
          write(6,*)' Invalid radar NetCDF schema'
          nf_status = nf_close(nf_fid)
          return
      endif

      call read_netcdf(nf_fid, V_bin_max, Z_bin_max, radial_max,
!............................................................................
     +     V, VCP, 
     +     Z, elevationNumber, numGatesV, numGatesZ, numRadials, 
     +     atmosAttenFactor, calibConst, elevationAngle, 
     +     firstGateRangeV, firstGateRangeZ, gateSizeV, gateSizeZ, 
     +     nyquist, powDiffThreshold, radialAzim, radialElev, 
     +     resolutionV, siteAlt, siteLat, siteLon, unambigRange, 
     +     esEndTime, esStartTime, radialTime, radarName, siteName,
     +     istatus)

      if(istatus .ne. 1)then
          write(6,*)' NetCDF variable read failed'
          return
      endif

      if(numRadials .lt. 1 .or. numRadials .gt. radial .or.
     +   numGatesV .lt. 1 .or. numGatesV .gt. V_bin_max .or.
     +   numGatesZ .lt. 1 .or. numGatesZ .gt. Z_bin_max .or.
     +   numGatesV .ne. numGatesZ)then
          write(6,*)' Invalid radar metadata shape/counts',numRadials,
     +        numGatesV,numGatesZ
          istatus = 0
          return
      endif

      if(.not.(firstGateRangeV .ge. 0. .and.
     +         firstGateRangeV .lt. 10. .and.
     +         firstGateRangeZ .ge. 0. .and.
     +         firstGateRangeZ .lt. 10. .and.
     +         abs(firstGateRangeV-firstGateRangeZ) .lt. 0.001 .and.
     +         gateSizeV .gt. 0. .and. gateSizeV .lt. 10. .and.
     +         gateSizeZ .gt. 0. .and. gateSizeZ .lt. 10. .and.
     +         abs(gateSizeV-gateSizeZ) .lt. 0.001))then
          write(6,*)' Invalid radar range geometry',firstGateRangeV,
     +        firstGateRangeZ,gateSizeV,gateSizeZ
          istatus = 0
          return
      endif

      if(.not.(elevationAngle .ge. 0. .and.
     +         elevationAngle .le. 90. .and.
     +         nyquist .gt. 0. .and. nyquist .lt. 1000. .and.
     +         siteAlt .ge. 0. .and. siteLat .ge. -90. .and.
     +         siteLat .le. 90. .and. siteLon .ge. -180. .and.
     +         siteLon .le. 180.))then
          write(6,*)' Invalid radar scalar metadata',elevationAngle,
     +        nyquist,siteAlt,siteLat,siteLon
          istatus = 0
          return
      endif

      do i=1,numRadials
          if(.not.(radialAzim(i) .ge. 0. .and.
     +             radialAzim(i) .lt. 360. .and.
     +             radialElev(i) .ge. -90. .and.
     +             radialElev(i) .le. 90. .and.
     +             radialTime(i) .eq. radialTime(i)))then
              write(6,*)' Invalid radial metadata at ray ',i
              istatus = 0
              return
          endif
      enddo

      if(sitealt .eq. 0. .or. sitelat .eq. 0. .or.
     +   sitelon .eq. 0.)then
          write(6,*)' Warning, no site info in tilt reader'
          istatus = 0
          return
      else
          write(6,*)' Site info:',siteAlt, siteLat, siteLon       
          istatus = 1
          return
      endif

      end
C
C
C
C  Subroutine to read the file "WSR-88D Wideband Data" 
C
      subroutine validate_radar_schema(nf_fid,V_bin,Z_bin,radial,
     + istatus)
      include 'netcdf.inc'
      integer nf_fid,V_bin,Z_bin,radial,istatus

      istatus = 1
      call validate_radar_var(nf_fid,'V',NF_FLOAT,2,V_bin,
     + radial,istatus)
      call validate_radar_var(nf_fid,'Z',NF_FLOAT,2,Z_bin,
     + radial,istatus)
      call validate_radar_var(nf_fid,'radialAzim',NF_FLOAT,1,radial,
     + -1,istatus)
      call validate_radar_var(nf_fid,'radialElev',NF_FLOAT,1,radial,
     + -1,istatus)
      call validate_radar_var(nf_fid,'radialTime',NF_DOUBLE,1,radial,
     + -1,istatus)
      call validate_radar_var(nf_fid,'radarName',NF_CHAR,1,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'siteName',NF_CHAR,1,-1,-1,
     + istatus)

      call validate_radar_var(nf_fid,'atmosAttenFactor',NF_FLOAT,0,
     + -1,-1,istatus)
      call validate_radar_var(nf_fid,'calibConst',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'elevationAngle',NF_FLOAT,0,
     + -1,-1,istatus)
      call validate_radar_var(nf_fid,'firstGateRangeV',NF_FLOAT,0,
     + -1,-1,istatus)
      call validate_radar_var(nf_fid,'firstGateRangeZ',NF_FLOAT,0,
     + -1,-1,istatus)
      call validate_radar_var(nf_fid,'gateSizeV',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'gateSizeZ',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'nyquist',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'powDiffThreshold',NF_FLOAT,0,
     + -1,-1,istatus)
      call validate_radar_var(nf_fid,'resolutionV',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'siteAlt',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'siteLat',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'siteLon',NF_FLOAT,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'unambigRange',NF_FLOAT,0,
     + -1,-1,istatus)
      call validate_radar_var(nf_fid,'VCP',0,0,-1,-1,istatus)
      call validate_radar_var(nf_fid,'elevationNumber',0,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'numGatesV',0,0,-1,-1,istatus)
      call validate_radar_var(nf_fid,'numGatesZ',0,0,-1,-1,istatus)
      call validate_radar_var(nf_fid,'numRadials',0,0,-1,-1,istatus)
      call validate_radar_var(nf_fid,'esEndTime',NF_DOUBLE,0,-1,-1,
     + istatus)
      call validate_radar_var(nf_fid,'esStartTime',NF_DOUBLE,0,-1,-1,
     + istatus)
      return
      end

      subroutine validate_radar_var(nf_fid,name,expected_type,
     + expected_rank,expected_dim1,expected_dim2,istatus)
      include 'netcdf.inc'
      integer nf_fid,expected_type,expected_rank,expected_dim1
      integer expected_dim2,istatus,nf_status,nf_vid,nf_type,nf_ndims
      integer nf_dimids(5),nf_natts,nf_dimlen
      character*(*) name
      character*132 actual_name

      nf_status = NF_INQ_VARID(nf_fid,name,nf_vid)
      if(nf_status .ne. NF_NOERR)then
          write(6,*)' Missing radar variable ',name
          istatus = 0
          return
      endif
      nf_status = NF_INQ_VAR(nf_fid,nf_vid,actual_name,nf_type,
     +                  nf_ndims,nf_dimids,nf_natts)
      if(nf_status .ne. NF_NOERR)then
          write(6,*)' Cannot inspect radar variable ',name
          istatus = 0
          return
      endif
      if(expected_type .eq. 0)then
          if(nf_type .ne. NF_SHORT .and. nf_type .ne. NF_INT)then
              write(6,*)' Wrong integer type for radar variable ',name,
     +                  nf_type
              istatus = 0
              return
          endif
      elseif(nf_type .ne. expected_type)then
          write(6,*)' Wrong type for radar variable ',name,nf_type
          istatus = 0
          return
      endif
      if(nf_ndims .ne. expected_rank)then
          write(6,*)' Wrong rank for radar variable ',name,nf_ndims
          istatus = 0
          return
      endif
      if(expected_rank .ge. 1)then
          nf_status = NF_INQ_DIMLEN(nf_fid,nf_dimids(1),nf_dimlen)
          if(nf_status .ne. NF_NOERR .or. nf_dimlen .lt. 1 .or.
     +       (expected_dim1 .gt. 0 .and.
     +        nf_dimlen .ne. expected_dim1))then
              write(6,*)' Wrong first dimension for radar ',name
              istatus = 0
              return
          endif
          if(expected_rank .ge. 2)then
              nf_status = NF_INQ_DIMLEN(nf_fid,nf_dimids(2),nf_dimlen)
              if(nf_status .ne. NF_NOERR .or. nf_dimlen .lt. 1 .or.
     +           (expected_dim2 .gt. 0 .and.
     +            nf_dimlen .ne. expected_dim2))then
                  write(6,*)' Wrong second dimension for radar ',name
                  istatus = 0
                  return
              endif
          endif
      endif
      return
      end

      subroutine read_netcdf(nf_fid, V_bin, Z_bin, radial, V, VCP, 
     +     Z, elevationNumber, numGatesV, numGatesZ, numRadials, 
     +     atmosAttenFactor, calibConst, elevationAngle, 
     +     firstGateRangeV, firstGateRangeZ, gateSizeV, gateSizeZ, 
     +     nyquist, powDiffThreshold, radialAzim, radialElev, 
     +     resolutionV, siteAlt, siteLat, siteLon, unambigRange, 
     +     esEndTime, esStartTime, radialTime, radarName, siteName,
     +     istatus)
C
      include 'netcdf.inc'
!     include 'remap_constants.dat' ! for debugging only
!     include 'remap.cmn' ! for debugging only
      integer V_bin, Z_bin, radial,nf_fid, nf_vid, nf_status
      integer istatus
      real V( V_bin, radial), Z( Z_bin, radial)
      integer VCP, elevationNumber, numGatesV, numGatesZ, numRadials
      real atmosAttenFactor, calibConst, elevationAngle,
     +     firstGateRangeV, firstGateRangeZ, gateSizeV, gateSizeZ,
     +     nyquist, powDiffThreshold, radialAzim(radial),
     +     radialElev(radial), resolutionV, siteAlt, siteLat,
     +     siteLon, unambigRange
      double precision esEndTime, esStartTime, radialTime(radial)
      character*5 radarName
      character*132 siteName

      istatus = 1

C   Variables of type REAL
C
C     Variable        NETCDF Long Name
C      atmosAttenFactor"Atmospheric attenuation factor"
C
        nf_status = NF_INQ_VARID(nf_fid,'atmosAttenFactor',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var atmosAttenFactor'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,atmosAttenFactor)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var atmosAttenFactor'
      endif
C
C     Variable        NETCDF Long Name
C      calibConst   "System gain calibration constant"
C
        nf_status = NF_INQ_VARID(nf_fid,'calibConst',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var calibConst'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,calibConst)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var calibConst'
      endif
C
C     Variable        NETCDF Long Name
C      elevationAngle"Elevation angle"
C
        nf_status = NF_INQ_VARID(nf_fid,'elevationAngle',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var elevationAngle'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,elevationAngle)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var elevationAngle'
      endif
C
C     Variable        NETCDF Long Name
C      firstGateRangeV"Range to 1st Doppler gate"
C
        nf_status = NF_INQ_VARID(nf_fid,'firstGateRangeV',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var firstGateRangeV'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,firstGateRangeV)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var firstGateRangeV'
      endif
C
C     Variable        NETCDF Long Name
C      firstGateRangeZ"Range to 1st Reflectivity gate"
C
        nf_status = NF_INQ_VARID(nf_fid,'firstGateRangeZ',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var firstGateRangeZ'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,firstGateRangeZ)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var firstGateRangeZ'
      endif
C
C     Variable        NETCDF Long Name
C      gateSizeV    "Doppler gate spacing"
C
        nf_status = NF_INQ_VARID(nf_fid,'gateSizeV',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var gateSizeV'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,gateSizeV)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var gateSizeV'
      endif

      gateSizeV = gateSizeV/1000.      !!! kys  
C
C     Variable        NETCDF Long Name
C      gateSizeZ    "Reflectivity gate spacing"
C
        nf_status = NF_INQ_VARID(nf_fid,'gateSizeZ',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var gateSizeZ'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,gateSizeZ)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var gateSizeZ'
      endif

      gateSizeZ = gateSizeZ/1000.      !!! source meters -> km
      firstGateRangeV = firstGateRangeV/1000.
      firstGateRangeZ = firstGateRangeZ/1000.
C
C     Variable        NETCDF Long Name
C      nyquist      "Nyquist velocity"
C
        nf_status = NF_INQ_VARID(nf_fid,'nyquist',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var nyquist'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,nyquist)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var nyquist'
      endif
C
C     Variable        NETCDF Long Name
C      powDiffThreshold"Range de-aliasing threshold"
C
        nf_status = NF_INQ_VARID(nf_fid,'powDiffThreshold',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var powDiffThreshold'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,powDiffThreshold)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var powDiffThreshold'
      endif
C
C     Variable        NETCDF Long Name
C      radialAzim   "Radial azimuth angle"
C
        nf_status = NF_INQ_VARID(nf_fid,'radialAzim',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radialAzim'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,radialAzim)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radialAzim'
      endif
C
C     Variable        NETCDF Long Name
C      radialElev   "Radial elevation angle"
C
        nf_status = NF_INQ_VARID(nf_fid,'radialElev',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radialElev'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,radialElev)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radialElev'
      endif
C
C     Variable        NETCDF Long Name
C      resolutionV  "Doppler velocity resolution"
C
        nf_status = NF_INQ_VARID(nf_fid,'resolutionV',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var resolutionV'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,resolutionV)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var resolutionV'
      endif
C
C     Variable        NETCDF Long Name
C      siteAlt      "Altitude of site above mean sea level"
C
        nf_status = NF_INQ_VARID(nf_fid,'siteAlt',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteAlt'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,siteAlt)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteAlt'
      endif
C
C     Variable        NETCDF Long Name
C      siteLat      "Latitude of site"
C
        nf_status = NF_INQ_VARID(nf_fid,'siteLat',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteLat'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,siteLat)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteLat'
      endif
C
C     Variable        NETCDF Long Name
C      siteLon      "Longitude of site"
C
        nf_status = NF_INQ_VARID(nf_fid,'siteLon',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteLon'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,siteLon)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteLon'
      endif
C
C     Variable        NETCDF Long Name
C      unambigRange "Unambiguous range"
C
        nf_status = NF_INQ_VARID(nf_fid,'unambigRange',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var unambigRange'
      endif
        nf_status = NF_GET_VAR_REAL(nf_fid,nf_vid,unambigRange)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var unambigRange'
      endif

C   Variables of type INT
C
C
C     Variable        NETCDF Long Name
C      V            "Velocity"
C
        nf_status = NF_INQ_VARID(nf_fid,'V',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var V'
      endif
        nf_status = NF_GET_VAR_real(nf_fid,nf_vid,V)    !!! kys
ckys    nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,V)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var V'
      endif
C
C     Variable        NETCDF Long Name
C      VCP          "Volume Coverage Pattern"
C
        nf_status = NF_INQ_VARID(nf_fid,'VCP',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var VCP'
      endif
        nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,VCP)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var VCP'
      endif
C
C     Variable        NETCDF Long Name
C      W            "Spectrum Width"
C
!        nf_status = NF_INQ_VARID(nf_fid,'W',nf_vid)
!      if(nf_status.ne.NF_NOERR) then
!        print *, NF_STRERROR(nf_status)
!        print *,'in var W'
!      endif
!        nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,W)
!      if(nf_status.ne.NF_NOERR) then
!        print *, NF_STRERROR(nf_status)
!        print *,'in var W'
!      endif
C
C     Variable        NETCDF Long Name
C      Z            "Reflectivity"
C
        nf_status = NF_INQ_VARID(nf_fid,'Z',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var Z'
      endif
        nf_status = NF_GET_VAR_real(nf_fid,nf_vid,Z)    !!! kys
ckys    nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,Z)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var Z'
      endif
C
C     Variable        NETCDF Long Name
C      elevationNumber"Elevation number"
C
        nf_status = NF_INQ_VARID(nf_fid,'elevationNumber',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var elevationNumber'
      endif
        nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,elevationNumber)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var elevationNumber'
      endif
C
C     Variable        NETCDF Long Name
C      numGatesV    "Number of Doppler gates"
C
        nf_status = NF_INQ_VARID(nf_fid,'numGatesV',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var numGatesV'
      endif
        nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,numGatesV)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var numGatesV'
      endif
C
C     Variable        NETCDF Long Name
C      numGatesZ    "Number of reflectivity gates"
C
        nf_status = NF_INQ_VARID(nf_fid,'numGatesZ',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var numGatesZ'
      endif
        nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,numGatesZ)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var numGatesZ'
      endif
C
C     Variable        NETCDF Long Name
C      numRadials   "Number of radials"
C
        nf_status = NF_INQ_VARID(nf_fid,'numRadials',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var numRadials'
      endif
        nf_status = NF_GET_VAR_INT(nf_fid,nf_vid,numRadials)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var numRadials'
      endif

C   Variables of type DOUBLE
C
C
C     Variable        NETCDF Long Name
C      esEndTime    "End time of elevation scan"
C
        nf_status = NF_INQ_VARID(nf_fid,'esEndTime',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var esEndTime'
      endif
        nf_status = NF_GET_VAR_DOUBLE(nf_fid,nf_vid,esEndTime)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var esEndTime'
      endif
C
C     Variable        NETCDF Long Name
C      esStartTime  "Start time of elevation scan"
C
        nf_status = NF_INQ_VARID(nf_fid,'esStartTime',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var esStartTime'
      endif
        nf_status = NF_GET_VAR_DOUBLE(nf_fid,nf_vid,esStartTime)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var esStartTime'
      endif
C
C     Variable        NETCDF Long Name
C      radialTime   "Time of radial"
C
        nf_status = NF_INQ_VARID(nf_fid,'radialTime',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radialTime'
      endif
        nf_status = NF_GET_VAR_DOUBLE(nf_fid,nf_vid,radialTime)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radialTime'
      endif


C   Variables of type CHAR
C
C
C     Variable        NETCDF Long Name
C      radarName    "Official name of the radar"
C
        nf_status = NF_INQ_VARID(nf_fid,'radarName',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radarName'
      endif
        nf_status = NF_GET_VAR_TEXT(nf_fid,nf_vid,radarName)
ckys    nf_status = NF_GET_VAR_TEXT(nf_fid,nf_vid,radarName)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var radarName'
      endif
C
C     Variable        NETCDF Long Name
C      siteName     "Long name of the radar site"
C
        nf_status = NF_INQ_VARID(nf_fid,'siteName',nf_vid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteName'
      endif
        nf_status = NF_GET_VAR_TEXT(nf_fid,nf_vid,siteName)
ckys    nf_status = NF_GET_VAR_TEXT(nf_fid,nf_vid,siteName)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'in var siteName'
      endif

      nf_status = nf_close(nf_fid)
      if(nf_status.ne.NF_NOERR) then
        istatus = 0
        print *, NF_STRERROR(nf_status)
        print *,'nf_close'
      endif

      return
      end
