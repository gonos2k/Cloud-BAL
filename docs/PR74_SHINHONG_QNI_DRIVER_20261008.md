# PR74 Shinhong QNI selected-driver research evidence

The PR73 research QNI patch was compiled into the actual selected Shinhong and
PBL driver (`pbl_driver`) modules from a fresh copy of the retained PR73 partialhost. The
maintained KIM sources were read-only. Both rebuilt objects were inserted into
a copied partialhost archive, checked byte-for-byte against their archive
members, and relinked with the captured WRF link command. The pinned Intel
runner repeated this at O0 and O2; see
`docs/evidence/pr74_shinhong_qni_driver_20261008.json`.

At `(i=133,j=2)`, the selected `pbl_driver` `SHINHONGSCHEME` call recorded
`QNC_ENABLED=T`, `QNI_ENABLED=T`, `p_qni=4`, and `num_scalar=6`. Five nonzero live QI/QNI levels at this capture point have individual ice mean masses from `2.37e-11` to `4.17e-10 kg` and are not a fixed QI scaling. The captured QNI profile is the preserved native input state. The routine returned its QI/QNI
transformed tendencies, and the driver recorded each `scalar_tend` update once
before writing `DRIVER_BRANCH_COMPLETE`. O0 and O2 produced identical driver
capture and pre-KDM6 trace hashes. The same 100 staged input hashes remained
unchanged.

The first KDM6 call still exits 128 with `KDM6 invalid NI number basis input`.
The new pretrace hash is `a6d5667850f5712982d5980b0292ee876b21cab6010efd18ade75cce5dfa1eaa`,
which differs from PR73's `d2331e90aee601dd9a1aa2549230fa7f388231ce224e53fdf60cb4b4b9b7e2bb`.
A read-only replay of the common Q/N pair predicate on the captured pretrace
places the hypothetical earliest mismatch at moment-only ice `(104,2,1)`, with
`QI=0` and `NI=3.8173049035872155e-36`. O0 and O2 captures match. This is not
an observed classifier failure: the actual wrapper unit adapter rejects the
NI basis before the common classifier. Positive `NI*rho_d` underflow remains
under investigation. The native run did not produce the required post-call
process, water, or next-time WRF output files. The predicate replay is in
`docs/evidence/pr74_shinhong_qni_moment_comparison_20261008.json`. The exact O0/O2
link argv, argv hashes, link-driver hash, and link-log hashes are bound in the
driver receipt. Both relinks inherit `-ftz`, `-O3`, and `-fp-model precise` from
the retained partialhost command, while the new Shinhong and driver objects
were compiled with pinned strict O0/O2 arrays and `-no-ftz`. The conversion
probe in `docs/evidence/pr74_common_moment_audit_20261008/ni_conversion_probe.json`
shows that strict no-FTZ preserves valid positive `NI*rho_d = 1.041735647987705e-38`
at `(211,2,15)`, while `-ftz` flushes that helper result to zero and rejects
the basis. This is relevant to the wrapper rejection but does not establish
that exact runtime fatal coordinate. The mixed partialhost link profile is not
a clean fullhost O0/O2 validation. This is a captured actual-driver path and a
native rejection, not a completed timestep or physical validation.

The new instrumentation patch in `docs/evidence/pr74_shinhong_qni_driver.patch`
adds a narrow source observer to the research driver copy. It records the
selected call gate, QI/QNI states and returned tendencies, each QNI tendency
addition, and completion of that branch. The physics changes come from the
separately recorded PR73 source patch. The compact routine fixture remains
secondary; it does not stand in for the driver run.

## Limits

- Only `module_bl_shinhong` and `module_pbl_driver` were rebuilt in the
  retained partialhost. The remaining host objects keep their captured build
  profile, and the relink inherits the baseline `-ftz` runtime setting, so this
  is not a clean full WRF build or a strict no-FTZ native validation.
- The runtime terminates at the KDM6 NI admission check before completed
  physics output. No whole-scheme conservation claim follows.
- The capture uses array coordinates `(133,2)`; global geographic mapping is
  unclaimed.
- The exact upstream producer of the first invalid QI/QNI state, `DEL` as the
  production dry-air carrier, and the out-of-range graupel policy remain open.
