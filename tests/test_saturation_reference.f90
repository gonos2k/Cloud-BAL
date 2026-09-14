! Cross-language fixture for the six-species saturation-adjustment kernel.
!
! The fixture intentionally contains only scalar records.  The Python checker
! reads each input state, solves the same physical equilibrium independently in
! temperature space, and compares the result written by this program.  The
! actual-transition cases additionally exercise the canonical float32 storage
! boundary that follows the production thermo solve.
!
! Records:
!   FORMAT SATURATION_REFERENCE_FIXTURE_V1
!   CASE name
!   INPUT pressure temperature target_rh surface
!   Q vapor liquid ice rain snow graupel
!   RESULT status temperature vapor liquid ice rain snow graupel
!   ENDCASE
!
! Each CASE contains its INPUT/Q records followed by the RESULT record.
PROGRAM test_saturation_reference
  USE, INTRINSIC :: iso_fortran_env, ONLY: real32,real64
  USE cloud_bal_state, ONLY: STATUS_OK
  USE cloud_bal_column_physics, ONLY: SATURATION_LIQUID,SATURATION_ICE, &
    saturation_adjust_mixture_cell
  IMPLICIT NONE

  CHARACTER(LEN=512) :: fixture_path
  REAL(real64) :: species(6)
  INTEGER :: fixture_unit,ios

  CALL GET_COMMAND_ARGUMENT(1,fixture_path)
  IF (LEN_TRIM(fixture_path)==0) fixture_path='saturation_reference_fixture.txt'

  OPEN(NEWUNIT=fixture_unit,FILE=TRIM(fixture_path),STATUS='NEW',ACTION='WRITE',IOSTAT=ios)
  IF (ios/=0) ERROR STOP 'open saturation fixture'

  WRITE(fixture_unit,'(A)') 'FORMAT SATURATION_REFERENCE_FIXTURE_V1'

  species=[0.0200_real64,0.0000_real64,0.0000_real64,0.0005_real64,0.0002_real64,0.0001_real64]
  CALL run_case('liquid_condensation',85000.0_real64,280.0_real64,species, &
    0.85_real64,SATURATION_LIQUID,fixture_unit)
  species=[0.0020_real64,0.0040_real64,0.0002_real64,0.0005_real64,0.0002_real64,0.0001_real64]
  CALL run_case('liquid_evaporation',85000.0_real64,280.0_real64,species, &
    0.95_real64,SATURATION_LIQUID,fixture_unit)
  species=[0.0020_real64,1.0e-8_real64,0.0000_real64,0.0000_real64,0.0000_real64,0.0000_real64]
  CALL run_case('liquid_reservoir_exhaustion',85000.0_real64,280.0_real64,species, &
    0.80_real64,SATURATION_LIQUID,fixture_unit)
  species=[0.0100_real64,0.0000_real64,0.0000_real64,0.0002_real64,0.0001_real64,0.0000_real64]
  CALL run_case('ice_deposition',85000.0_real64,255.0_real64,species, &
    0.80_real64,SATURATION_ICE,fixture_unit)
  species=[0.0002_real64,0.0000_real64,0.0030_real64,0.0002_real64,0.0000_real64,0.0000_real64]
  CALL run_case('ice_sublimation',85000.0_real64,255.0_real64,species, &
    1.00_real64,SATURATION_ICE,fixture_unit)
  species=[0.0040_real64,0.0000_real64,0.0010_real64,0.0002_real64,0.0000_real64,0.0000_real64]
  CALL run_case('invalid_ice_warming',85000.0_real64,280.0_real64,species, &
    0.90_real64,SATURATION_ICE,fixture_unit)

  ! A near-zero transfer root: the floating-point bracket can stagnate before
  ! the residual reaches the ordinary finite-width stopping condition.
  species=[0.005870999793457342_real64,0.0040_real64,0.0_real64,0.0_real64,0.0_real64,0.0_real64]
  CALL run_case('nearzero_transfer_root',85000.0_real64,280.0_real64,species, &
    0.80_real64,SATURATION_LIQUID,fixture_unit)

  ! These nine scalar states are the cloud-water ULP residual cells from the
  ! 2026-08-16_13 transition replay.  Keep the input values at their original
  ! float32 payloads, and canonicalize the solver result as production does.
  species=[0.010708491317927837_real64,0.0006279909866861999_real64,0.0_real64, &
    0.000034973312722286209_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_max_q',75000.0_real64,283.6981201171875_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.019398108124732971_real64,0.00002551486250013113_real64,0.0_real64, &
    0.000037931236875010654_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p100000',100000.0_real64,297.43756103515625_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.018441606312990189_real64,0.00044167719897814095_real64,0.0_real64, &
    0.00010537877096794546_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p95000_a',95000.0_real64,295.88156127929688_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.017254306003451347_real64,0.00016551195585634559_real64,0.0_real64, &
    0.000029057198844384402_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p95000_b',95000.0_real64,294.81948852539062_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.017005102708935738_real64,0.0004378845333121717_real64,0.0_real64, &
    0.000047373661800520495_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p95000_c',95000.0_real64,294.58819580078125_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.015416937880218029_real64,0.000047797653678571805_real64,0.0_real64, &
    0.0000093061180450604297_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p95000_d',95000.0_real64,293.037841796875_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.015929939225316048_real64,0.000049443537136539817_real64,0.0_real64, &
    0.000076174452260602266_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p95000_e',95000.0_real64,293.55380249023438_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.014020812697708607_real64,0.0000031989773106033681_real64,0.0_real64, &
    0.0000086995987658156082_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p80000',80000.0_real64,288.69403076171875_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)
  species=[0.0088775064796209335_real64,0.00034867800422944129_real64,0.0_real64, &
    0.0000056243943618028425_real64,0.0_real64,0.0_real64]
  CALL run_case('actual_transition_p65000',65000.0_real64,279.54592895507812_real64,species, &
    1.0_real64,SATURATION_LIQUID,fixture_unit,.TRUE.)

  CLOSE(fixture_unit)
  WRITE(*,'(A)') 'SATURATION REFERENCE FIXTURES PASS'
  WRITE(*,'(A)') '  fifteen valid cases; one invalid atomic case'

CONTAINS

  SUBROUTINE run_case(name,pressure,temperature,species,target_rh,surface,fixture_unit,canonical_storage)
    CHARACTER(*), INTENT(IN) :: name
    REAL(real64), INTENT(IN) :: pressure,temperature,species(6),target_rh
    INTEGER, INTENT(IN) :: surface,fixture_unit
    LOGICAL, INTENT(IN), OPTIONAL :: canonical_storage
    REAL(real64) :: adjusted_temperature,adjusted_species(6)
    INTEGER :: status

    WRITE(fixture_unit,'(A,1X,A)') 'CASE',TRIM(name)
    WRITE(fixture_unit,'(A,1X,3(ES24.16,1X),I0)') 'INPUT',pressure,temperature,target_rh,surface
    WRITE(fixture_unit,'(A,1X,6(ES24.16,1X))') 'Q',species

    adjusted_temperature=temperature
    adjusted_species=species
    CALL saturation_adjust_mixture_cell(pressure,adjusted_temperature,adjusted_species, &
      target_rh,status,surface)

    IF (PRESENT(canonical_storage)) THEN
      IF (canonical_storage .AND. status==STATUS_OK) THEN
        adjusted_temperature=REAL(REAL(adjusted_temperature,real32),real64)
        adjusted_species=REAL(REAL(adjusted_species,real32),real64)
      END IF
    END IF

    WRITE(fixture_unit,'(A,1X,I0,1X,7(ES24.16,1X))') 'RESULT',status, &
      adjusted_temperature,adjusted_species
    WRITE(fixture_unit,'(A)') 'ENDCASE'
  END SUBROUTINE run_case

END PROGRAM test_saturation_reference
