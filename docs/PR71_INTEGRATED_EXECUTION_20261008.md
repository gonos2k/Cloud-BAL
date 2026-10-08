# PR71 integrated execution evidence (2026-10-08)

## Source composition

The integrated candidate composes the selected PR68 source with the PR70 process change and PR69 density routing, then applies the PR71 particle-output validity patch and checked substep-count patch. The resulting selected-KDM6 source SHA-256 is `6245969c87f6568cad3b6c6afddc0d1bdfe84a31baa1cee10a465b663c88d716`. The PR71 particle validity patch SHA-256 is `94ea6189c85cd0856a28aac2663ad70091c3259fc448d48bd021adf42ff9ae45`; the checked substep-count patch SHA-256 is `7bc37047bf616b50ebb506f130a2f1f0535e0a5afc26bb26183a27ee188ebb24`.

The particle interface initializes its outputs on every call and returns a per-cell status. Callers consume particle values only for `PSD_ACTIVE`; `ABSENT` uses inert graupel slope/velocity terms, and transient or unsupported states stop before dependent reads. The checked substep helper validates finite rates and timestep plus signed default-integer representability before `NINT`. For inputs in the representable domain it retains the existing `max(nint(rate*dtcld+0.5),1)` result. It adds no CFL limit, rate cap, or velocity policy.

## Full-module fixtures

[Guarded unit and process integration receipt](evidence/pr71_unit_process_guarded_integration_20261008.json) records the fresh Intel `ifx` O0/O2 runs. Four preserved density states (0.25, 0.50, 1.00, and 2.00 kg m-3) pass candidate/direct-volume comparisons. An EOS-consistent active case also passes candidate/direct-volume comparison at p=90000 Pa and T=250 K. The driver derives dry density as `rho_d = p/[Rd*T*(1+qv/epsilon)]`, with `Rd=287.04` and `epsilon=0.622`, then supplies moist density as `DEN = rho_d*(1+qv)`; the receipt records the vapor source and calculated values. These are fixture results, not a full atmospheric integration.

The rain public-number fixture now uses the source coefficient `cmr*Gamma(1+dmr+mur)/Gamma(1+mur) = cmr*24` for `mur=1, dmr=3`. This corrects the fixture’s prior description of its rain lambda; the earlier PR70 conversions and receipts remain historical. The PR71 driver correction does not alter the PR70 tests or receipts.

The separate EOS graupel-absent full-module fixture is **blocked** by the inherited `n0i` divide by zero in `kdm62d` at line 2106, before output comparison. It has rain, graupel, and background graupel set to zero while cloud and ice are positive. This does not establish full-module absent-graupel behavior; the focused output-contract harness and source-consumer guards remain the scoped evidence for that case.

## Native firstcall

[Guarded partialhost native receipt](evidence/pr71_guarded_native_integration_20261008.json) binds the exact combined source, observer-only source transform, fresh Intel KDM6 object, executable, retained input hashes, and run outputs. The native firstcall returned `EXPECTED_STEP_COUNT_CONTRACT_REJECT`: the ice check reported `i=107`, `k=5`, rate `829940373.290303 s-1`, and `dt=20 s`, then stopped with `invalid PR71 KDM6 ice substep count` before the unsafe integer conversion. All 100 staged input files retained their hashes. The `pr67_kdm6_process.raw` and `pr69_water.raw` outputs are absent because execution stopped before those diagnostics completed.

This controlled numeric-domain rejection confirms that the observed out-of-range conversion is caught before `NINT`. It does not establish an accepted model, particle-property, or freezing solution, and it does not establish physical closure. The build is partialhost: selected KDM6 was recompiled and inserted into retained host objects/archive, with external MPI, WRF, NetCDF, and other link dependencies retained rather than rebuilt as a complete dependency closure.

The earlier v1 bounded run and v2 diagnostic run are retained as [v1 incomplete evidence](evidence/pr71_native_v1_incomplete_20261008.json) and [v2 incomplete observation](evidence/pr71_native_v2_incomplete_observation_20261008.json). Both ended without a PR71 contract rejection or accepted model completion; v1's old stage-0 `work1(:,:,4)` field is explicitly untrusted. V2 independently observed an out-of-range source NINT input at `(i=78,k=2)`; it did not capture the pre-NINT driver associated with the separate maximum step result at `i=149`.

Scientific approval remains **FAIL_OPEN**. The native controlled rejection and fixture passes do not resolve the remaining ice-velocity model cause or establish full-physics validity.
