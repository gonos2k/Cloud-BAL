! Cloud-layer detection and multi-layer vertical-motion profiles.
MODULE cloud_bal_cloud_profiles
  USE, INTRINSIC :: ieee_arithmetic, ONLY: ieee_is_finite
  IMPLICIT NONE
  PRIVATE
  PUBLIC :: detect_cloud_layers
  PUBLIC :: build_multilayer_w_profile

CONTAINS

  SUBROUTINE detect_cloud_layers(cloud_type, max_layers, n_layers, &
                                 layer_bottom, layer_top, status)
    INTEGER, INTENT(IN) :: cloud_type(:), max_layers
    INTEGER, INTENT(OUT) :: n_layers, layer_bottom(max_layers), &
                            layer_top(max_layers), status
    INTEGER :: k, nk
    LOGICAL :: in_layer

    nk = SIZE(cloud_type)
    n_layers = 0
    layer_bottom = 0
    layer_top = 0
    status = 1
    in_layer = .FALSE.

    DO k = 1, nk
      IF (cloud_type(k) > 0 .AND. .NOT. in_layer) THEN
        IF (n_layers == max_layers) THEN
          status = 0
          RETURN
        END IF
        n_layers = n_layers + 1
        layer_bottom(n_layers) = k
        in_layer = .TRUE.
      END IF
      IF (in_layer .AND. (cloud_type(k) <= 0 .OR. k == nk)) THEN
        IF (cloud_type(k) <= 0) THEN
          layer_top(n_layers) = k - 1
        ELSE
          layer_top(n_layers) = k
        END IF
        in_layer = .FALSE.
      END IF
    END DO
  END SUBROUTINE detect_cloud_layers

  SUBROUTINE build_multilayer_w_profile(dx_km, cloud_type, height, &
                                        ratio_cu, ratio_sc, w_stratus, &
                                        missing, w, status)
    REAL, INTENT(IN) :: dx_km, height(:), ratio_cu, ratio_sc, &
                        w_stratus, missing
    INTEGER, INTENT(IN) :: cloud_type(:)
    REAL, INTENT(OUT) :: w(:)
    INTEGER, INTENT(OUT) :: status
    INTEGER :: bottom(SIZE(cloud_type)), top(SIZE(cloud_type))
    INTEGER :: n_layers, layer, k, kb, kt
    REAL :: depth, z0, z1, eta, amplitude, pi
    LOGICAL :: convective, precipitating_stratiform

    status = 0
    w = missing
    IF (SIZE(height) /= SIZE(cloud_type) .OR. SIZE(w) /= SIZE(cloud_type)) RETURN
    IF (dx_km <= 0.0 .OR. .NOT. ieee_is_finite(dx_km)) RETURN
    IF (ANY(.NOT. ieee_is_finite(height))) RETURN
    IF (SIZE(height) > 1) THEN
      IF (ANY(height(2:) <= height(:SIZE(height)-1))) RETURN
    END IF

    CALL detect_cloud_layers(cloud_type, SIZE(cloud_type), n_layers, &
                             bottom, top, status)
    IF (status /= 1) RETURN
    pi = ACOS(-1.0)

    DO layer = 1, n_layers
      kb = bottom(layer)
      kt = top(layer)
      IF (kb > 1) THEN
        z0 = 0.5 * (height(kb-1) + height(kb))
      ELSE IF (SIZE(height) > 1) THEN
        z0 = height(1) - 0.5*(height(2)-height(1))
      ELSE
        z0 = height(1) - 0.5
      END IF
      IF (kt < SIZE(height)) THEN
        z1 = 0.5 * (height(kt) + height(kt+1))
      ELSE IF (SIZE(height) > 1) THEN
        z1 = height(kt) + 0.5*(height(kt)-height(kt-1))
      ELSE
        z1 = height(kt) + 0.5
      END IF
      depth = MAX(1.0, z1 - z0)
      convective = ANY(cloud_type(kb:kt) == 3 .OR. &
                       cloud_type(kb:kt) == 10 .OR. &
                       cloud_type(kb:kt) == 11)
      precipitating_stratiform = ANY(cloud_type(kb:kt) == 4)

      DO k = kb, kt
        IF (kt == kb) THEN
          eta = 0.5
        ELSE
          eta = MIN(1.0, MAX(0.0, (height(k)-z0)/depth))
        END IF
        IF (convective) THEN
          amplitude = MAX(w_stratus, ratio_cu * depth / dx_km)
          w(k) = MAX(w_stratus, amplitude * SIN(pi*eta))
        ELSE IF (precipitating_stratiform) THEN
          amplitude = MAX(w_stratus, ratio_sc * depth / dx_km)
          IF (eta < 0.40) THEN
            ! Evaporation/melting-supported lower-layer descent.
            w(k) = -0.25 * amplitude * SIN(pi*eta/0.40)
          ELSE
            w(k) = amplitude * SIN(pi*(eta-0.40)/0.60)
          END IF
        ELSE
          w(k) = w_stratus
        END IF
      END DO
    END DO
    status = 1
  END SUBROUTINE build_multilayer_w_profile

END MODULE cloud_bal_cloud_profiles
