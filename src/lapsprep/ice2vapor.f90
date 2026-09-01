  SUBROUTINE ice2vapor(ice,sh,t,p,thresh,ice_m,sh_m,rh_m)

    USE cloud_bal_moisture, ONLY: evaporate_to_target

  ! Subroutine to convert cloud ice to vapor up to a saturation
  ! threshold (wrt ice)

    IMPLICIT NONE

    ! Inputs:

    REAL, INTENT(IN)    :: ice    ! Cloud ice mixing ratio (kg/kg)
    REAL, INTENT(IN)    :: sh     ! Specific humidity (kg/kg)   
    REAL, INTENT(IN)    :: t      ! Temperature (K)
    REAL, INTENT(IN)    :: p      ! Pressure (Pa)
    REAL, INTENT(IN)    :: thresh ! Saturation factor    
              ! Set thresh to 1.0 to convert cloud ice up to
              ! ice saturation

    ! Outputs:
   
    REAL, INTENT(OUT)   :: ice_m  ! Adjusted lwc
    REAL, INTENT(OUT)   :: sh_m   ! Adjusted specific humidity
    REAL, INTENT(OUT)   :: rh_m   ! Adjusted RH (%)

    ! Locals

    REAL :: shsat,mr,mrsat,mr_m,mrmax,tc
    INTEGER :: transfer_status
    REAL, EXTERNAL :: ssh2,make_rh

    
    ! Set saturation specific humidity for ice for this point         
    tc = t-273.15
    shsat = ssh2(p,tc,tc,0.)*0.001
   
    ! Convert specific humidity to mixing ratio 
    ice_m = MAX(0.0,ice)
    sh_m = sh
    rh_m = 0.0
    IF (shsat .LE. 0. .OR. shsat .GE. 1. .OR. &
        sh .LT. 0. .OR. sh .GE. 1. .OR. p .LE. 0. .OR. &
        thresh .LT. 0.) RETURN

    mrsat = shsat/(1.-shsat)
    mr = sh/(1.-sh)
    mrmax = mrsat*thresh

    ! Sublimate only available ice and preserve vapor plus ice exactly.
    mr_m = mr
    CALL evaporate_to_target(mr_m,ice_m,mrmax,transfer_status)
    IF (transfer_status .NE. 1) RETURN

    rh_m = (mr_m/mrsat)*100.

    ! Convert mr_m to sh_m
    sh_m = mr_m/(1.+mr_m) 
    RETURN
  END SUBROUTINE ice2vapor
