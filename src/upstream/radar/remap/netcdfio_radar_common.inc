
       real Z(MAX_REF_GATES*MAX_RAY_TILT)
       real V(MAX_VEL_GATES*MAX_RAY_TILT)
       real W(MAX_VEL_GATES*MAX_RAY_TILT)
       real T(MAX_TID_GATES*MAX_RAY_TILT)         !add by why(forBB)
       real radialAzim(MAX_RAY_TILT)
       real radialElev(MAX_RAY_TILT)
       real elevationAngle,siteLat,siteLon,siteAlt,unambigRange
       real firstGateRangeZ, firstGateRangeV
       real firstGateRangeT                      !add by why(forBB)
       real gateSizeZ, gateSizeV
       real gateSizeT                            !add by why(forBB)
       real resolutionV, nyquist, calibConst
       real atmosAttenFactor, powDiffThreshold

       double precision radialTime(MAX_RAY_TILT)
       double precision esStartTime, esEndTime

       integer elevationNumber,numRadials,VCP,numGatesZ,numGatesV
       integer numGatesT

       character*5 radarName
       character*16 siteName

       common/radar_tilt_data/
     1                        siteLat
     1                       ,siteLon
     1                       ,siteAlt
     1                       ,elevationAngle
     1                       ,elevationNumber
     1                       ,VCP
     1                       ,nyquist
     1                       ,radialAzim
     1                       ,Z
     1                       ,V
     1                       ,resolutionV
     1                       ,gateSizeV,gateSizeZ
     1                       ,firstGateRangeV,firstGateRangeZ
c    1                       ,i4time_process
     1                       ,numRadials
     1                       ,radarName
     1                       ,T               ! add by why(forBB)
     1                       ,gateSizeT       ! add by why(forBB)
     1                       ,firstGateRangeT ! add by why(forBB)
c
c     These two values are part of the consumer state.  Keep them at the
c     end so the legacy fields retain their established common-block offsets.
     1                       ,numGatesZ
     1                       ,numGatesV
