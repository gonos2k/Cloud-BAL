PROGRAM test_kdm6_number_density_invariance
  USE module_mp_kdm6, ONLY: kdm6init, effectRad_kdm6
  USE module_mp_radar, ONLY: xam_g
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  REAL :: temperature(3), cloud(3), cloud_number(3), ice(3), ice_number(3)
  REAL :: snow(3), density(3), cloud_radius(3), ice_radius(3), snow_radius(3)

  ! Equal kg/kg and #/kg imply the same particle mass at every air density.
  temperature = 260.0
  cloud = 1.0e-4
  cloud_number = 1.0e7
  ice = 1.0e-3
  ice_number = 1.0e5
  snow = 0.0
  density = [0.5, 1.0, 2.0]
  cloud_radius = 0.0
  ice_radius = 0.0
  snow_radius = 0.0
  ! This cloud/ice oracle supplies the unrelated radar initialization constant
  ! using kdm6init's default graupel density; it does not test graupel startup.
  xam_g = ACOS(-1.0)*500.0/6.0
  CALL kdm6init(1.28, 1000.0, 100.0, 4190.0, 1846.4, 1.0e8, 0, .FALSE.)
  CALL effectRad_kdm6(temperature, cloud, cloud_number, ice, ice_number, &
       snow, density, 1.0e-12, 273.15, cloud_radius, ice_radius, snow_radius, &
       1, 3, 1, 1)
  PRINT *, 'Cloud radii:', cloud_radius
  PRINT *, 'Ice radii:', ice_radius
  IF (.NOT.ALL(ieee_is_finite(cloud_radius))) ERROR STOP 1
  IF (.NOT.ALL(ieee_is_finite(ice_radius))) ERROR STOP 2
  ! Stay away from clipping bounds: a clipped constant is not this oracle.
  IF (ANY(cloud_radius <= 2.51e-6 .OR. cloud_radius >= 50.0e-6)) ERROR STOP 3
  IF (ANY(ice_radius <= 10.01e-6 .OR. ice_radius >= 125.0e-6)) ERROR STOP 4
  IF (MAXVAL(ABS(cloud_radius-cloud_radius(2))) > 1.0e-10) ERROR STOP 5
  IF (MAXVAL(ABS(ice_radius-ice_radius(2))) > 1.0e-10) ERROR STOP 6
  PRINT *, 'KDM6 specific-number density invariance passed'
END PROGRAM test_kdm6_number_density_invariance
