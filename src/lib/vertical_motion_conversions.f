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
cdis    Extracted from the KLAPS conversions.f translation unit for the
cdis    focused Cloud-BAL baseline. Function bodies are unchanged.

        function omega_to_w(omega,pressure_pa)

cdoc    Convert Omega to W

        real*4 omega_to_w

        real*4 scale_height
        parameter (scale_height = 8000.)

        omega_to_w = - (omega / pressure_pa) * scale_height

        return
        end

        function w_to_omega(w,pressure_pa)

cdoc    Convert W to Omega

        real*4 w_to_omega

        real*4 scale_height
        parameter (scale_height = 8000.)

        w_to_omega = - (w * pressure_pa) / scale_height

        return
        end
