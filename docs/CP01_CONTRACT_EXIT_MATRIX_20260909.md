# CP01 contract exit matrix — 2026-09-09

Status: **COMPLETE / PASS — bounded research contract and small tests**.
All six original CP01 criteria are met at their stated scope. This is not
accepted native handoff, a full writer, operational equivalence, or final
M01–M07 science acceptance. The real 13 UTC input remains `NO_AUTHORITY`.

| Original CP01 criterion | Disposition and evidence | Downstream boundary |
|---|---|---|
| 1. Host/version, species/basis, staggering, boundaries, binaries and coordinates | PASS: [host/species binding](CP01_HOST_SPECIES_BINDING_20260909.md), [private profile](CP01_PRIVATE_HOST_PROFILE_20260909.md), 53 artifact identities checked | Dirty source checkout and historical runtime identity are distinguished; private periodic probe is not specified-boundary equivalence |
| 2. Canonical/WPS/native mapping, dry mass, pressure/EOS, A_Q/A_M/A_E units | PASS: [native contract](NATIVE_MASS_FRAME_CONTRACT.md), [mass/frame binding](CP01_MASS_FRAME_BINDING_20260909.md), exact [T/THM replay](CP01_THETA_BINDING_20260909.md), independent native metric review and asymmetric boundary-flux oracle | Face flux metrics remain separate; full timestep mass/energy closure remains CP06/07 |
| 3. Diagnostic/native mass separation and optional species coverage | PASS: five auxiliary fields and four mass/moment pairs declared; maintained preflight checks native bytes, declarations and units; actual input rejected before transaction | Constructed positive publishes diagnostic receipt only; producer authentication and launch integration remain downstream |
| 4. Independent cell_dp, center, partial-face, thin-cell and PSFC oracle | PASS: frozen O0/O2 plus independent Python receipt `scratch/cp01_contract_snapshot.hvp19t_7/receipt.json`; 36 relevant live source hashes and 106 retained artifacts match | Native state-dependent coordinate reconstruction remains CP06/07 |
| 5. Frame, rotation/map factors, w/omega, boundary/time and ww distinction | PASS: mass/frame binding and retained time/boundary receipts; all 56 latest reader-suite source hashes match | Unknown historical physical authority stays unusable; native ww continuity reconstruction is assigned CP06-B |
| 6. Small positive/negative contract tests | PASS: retained moist column, impulse, slope, missing OM/domain and units tests; 19 native preflight, 21 shared MP37 tests, output transaction suite and independent metric test | No full forecast, release or final science claim |

The final [completion audit](CP01_COMPLETION_AUDIT_20260909.md) binds the
receipts in `scratch/cp01_final_binding_vpoe3vby/`, including independent
`red_review.md` and `green_review.md`, source snapshots, full focused logs,
and the actual-input rejection receipt. The red review assessed all six
criteria; green independently reviewed preflight implementation and evidence.

Actual-input rejection preserved all prior generation file hashes, the
current pointer and input bytes, with no new generation or launch marker.
This atomicity evidence uses local scratch storage. NAS prior-generation
seeding failed the existing atomic no-replace filesystem requirement and is
explicitly excluded from publication-readiness claims. CP02 must establish
a supported and verified publication path; the guard was not weakened.

The private profile supplies no implicit QNCLOUD/QNICE/QNRAIN/QIB initializer.
Its explicit dry-air denominator contract and fail-closed startup rule complete
the definition; they do not make the rejected actual input acceptable.
The six CP01 criteria do not require a full launcher, forecast, clean full-host
rebuild or native energy-conservation run. Those downstream criteria remain
in force and are not waived by this exit.
