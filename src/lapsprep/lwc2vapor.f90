  SUBROUTINE lwc2vapor(lwc,sh,t,p,thresh,lwc_m,sh_m,rh_m)

    USE cloud_bal_moisture, ONLY: evaporate_to_target

  ! Subroutine to convert cloud water to vapor.

    IMPLICIT NONE

    ! Inputs:

    REAL, INTENT(IN)    :: lwc    ! Cloud water mixing ratio (kg/kg)
    REAL, INTENT(IN)    :: sh     ! Specific humidity (kg/kg)   
    REAL, INTENT(IN)    :: t      ! Temperature (K)
    REAL, INTENT(IN)    :: p      ! Pressure (Pa)
    REAL, INTENT(IN)    :: thresh ! Saturation factor    
              ! Set thresh to 1.0 to convert cloud water up to
              ! vapor saturation.  1.1 will allow 110% RH, and so
              ! forth

    ! Outputs:
   
    REAL, INTENT(OUT)   :: lwc_m  ! Adjusted lwc
    REAL, INTENT(OUT)   :: sh_m   ! Adjusted specific humidity
    REAL, INTENT(OUT)   :: rh_m   ! Adjusted RH (%)

    ! Locals

    REAL :: shsat,mrmax,mr,mr_m,mrsat
    INTEGER :: transfer_status
    REAL, EXTERNAL :: ssh,make_rh

    
    ! Set saturation specific humidity for this point         

    shsat = ssh(p,t-273.15)*0.001
 
    ! Convert specific humidity to mixing ratio 
    lwc_m = MAX(0.0,lwc)
    sh_m = sh
    rh_m = 0.0
    IF (shsat .LE. 0. .OR. shsat .GE. 1. .OR. &
        sh .LT. 0. .OR. sh .GE. 1. .OR. p .LE. 0. .OR. &
        thresh .LT. 0.) RETURN

    mrsat = shsat/(1.-shsat)
    mr = sh/(1.-sh)
     
    mrmax = mrsat*thresh

    ! Transfer only the mass needed to reach the target.  Vapor plus liquid
    ! is invariant; supersaturated vapor is never deleted.
    mr_m = mr
    CALL evaporate_to_target(mr_m,lwc_m,mrmax,transfer_status)
    IF (transfer_status .NE. 1) RETURN

    ! Compute RH from modified mixing ratio
    rh_m = (mr_m/mrsat)*100.

    ! Convert modified mixing ratio back to specific humidity
    sh_m = mr_m/(1.+mr_m)

    RETURN
  END SUBROUTINE lwc2vapor
