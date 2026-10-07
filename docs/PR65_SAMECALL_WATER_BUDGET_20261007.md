# PR65 same-call KDM6 water and energy audit

## Result

This audit uses the exact-source NC donor observer control in
`/var/tmp/pr65_nc_donors_20261007/run_guarded_final`. It is separate from the
new shared-NC PBL experiment. Its storage changes must not be attributed to
the PBL change or combined with that experiment's moment metrics as one
candidate's budget.

The isolated PR65 run's same-call KDM6 pre/post traces and matching `pr63_geometry.raw` were integrated using the hybrid dry-air carrier derived from the captured host geometry. The exact measure is

`sum(dp_k * DX*DY/(MSFTX*MSFTY) / g)`, with `dp_k = -[C1H_k*(MU2+MUB)+C2H_k]*DNW_k`.

The geometry audit binds the PRE/POST geometry records to the same timestep-1 KDM6 call (`dtm=DELT=20 s`), the captured KDM6 bounds, the guarded-run receipt, and executable SHA-256. Geometry arrays and KDM `DEN`/`DELZ` are unchanged across the call. The active hybrid dry-air mass measure is `1.6204030034989606e16 kg`.

Using that same carrier at both endpoints, the captured water species `Q+QC+QR+QI+QS+QG` decrease from `9.298041245598061e13 kg` to `9.16893004751316e13 kg`, a change of `-1.291111980849e12 kg` (`-1.3885849%`). The component changes are:

| KDM field | Integrated species mass change |
| --- | ---: |
| Q (water vapor) | `+5.82717022207e11 kg` |
| QC (cloud water) | `-6.65780902113e11 kg` |
| QR (rain) | `+3.86015341240e10 kg` |
| QI (cloud ice) | `-1.28413937637e12 kg` |
| QS (snow) | `+1.47808782718e10 kg` |
| QG (graupel) | `+2.27088630349e10 kg` |

These are endpoint storage changes, not a closed microphysics budget. Large phase redistribution is visible, but the capture lacks the same-call precipitation accumulator increments or bottom sedimentation flux needed to compare column water loss against precipitation leaving the atmospheric column. The KDM source accepts and updates `rainncv` plus optional `snowncv` and `graupelncv`; its falling-flux code increments those outputs. Their values are absent from the pre/post trace schema. The guarded output manifest contains a `wrfout` artifact, but no per-call precipitation increment is bound to this KDM6 call; it is excluded from this same-call calculation. Source inspection identifies candidate terms but cannot supply their missing runtime values.

The input KDM6 trace contains `23,494` negative QC values. The inspected source clips incoming cloud water to zero at call entry; weighting only those negative inputs by the hybrid dry-air mass gives a `+2.124452e6 kg` storage correction if clipped. The post trace has no negative QC. This estimated entry cleanup is only about `1.65e-6` of the magnitude of the observed net total-water decrease, and it is not a complete process decomposition. It does not explain the full water delta.

The KDM6 source interface and unit comments identify the next useful runtime capture: `rainncv`, and optional `snowncv` and `graupelncv`, are output accumulators reset at call start. Falling flux adds surface increments in millimeters (`fall*DELZ/denr*dtcld*1000`) at the lower interface. Capturing these pre/post accumulators with the atmospheric endpoint state would test whether sedimentation accounts for the storage decrease; an entry cleanup and phase-transfer ledger would still be needed to close the remaining residual.

I did not build or run a new instrumented KDM6 object. The PR65 run uses archived member `module_mp_kdm6.o` (SHA-256 `7717a8531a40b42fa46b9c7fe2be57a844e4692ab820dcf1728a0b3170c971f2` from the guarded archive); it matches the same member in the PR64 base archive byte-for-byte. The retained source/member hashes and this equality are recorded in [the member binding note](evidence/pr65_kdm6_member_binding_20261007.sha256). The maintained source inspected for the interface is `KIM_RDPS_MODL_V2026.2/phys/module_mp_kdm6.F` (SHA-256 `02c9dc1f6711c9785d3c5841cbf2c14ebc454fa4628466407ae7f8879e965c5a`), but no retained compile record binds this source to that PR65 archive member. The existing call-duration evidence also leaves the compiled microphysics-driver object source binding unverified. Recompiling the maintained source and replacing only this member would therefore introduce a source/object equivalence question into the science run. A source-bound capture requires a frozen KDM6 source, compiler invocation and include/module set, instrumented object hash, an uninstrumented control built from the same source, and guarded same-input runs showing unchanged pre/post scientific fields before interpreting accumulator deltas.

## Measures and thermodynamic diagnostics

The separately computed `DEN*DELZ*area` diagnostic is reported as a distinct volume-style measure; it is not substituted for the source-defined hybrid dry-air carrier used for water species integration. Promoting stored `DEN` and `DELZ` operands to float64 before multiplication gives `1.6213518543290812e16 kg` at both endpoints, `+0.05855647%` relative to hybrid dry-air mass. The existing geometry audit multiplies those stored REAL*4 operands before area scaling and reports `1.6213518543367404e16 kg`. The two arithmetic orders differ by `-76,592 kg` (`-4.73e-12` of hybrid mass). This is numerical-order sensitivity in the diagnostic, not a physical tolerance or closure result; the earlier geometry receipt's value is preserved.

`T=TH*PII` reconstructed in float64 from captured REAL*4 operands changes in 1,184,042 cells, with maximum absolute change about `3.229 K` and dry-mass-weighted mean change `-0.08751 K`. This is a temperature diagnostic, not an energy budget. The capture does not include a same-call per-process thermodynamic tendency ledger, latent/sensible enthalpy accounting, or precipitation enthalpy flux. It therefore cannot establish energy closure. No expected-zero energy change was assumed.

## What remains open

- **Water mass closure: OPEN.** Capture per-call rain, snow, and graupel accumulator increments (or equivalent vertically integrated bottom flux), then reconcile those with endpoint storage and the per-process cleanup/phase-transfer ledger. Current source provides the output interface and millimeter accumulation formula; PR65 archive-object/source binding prevents a new observer claim from this source alone.
- **Energy closure: OPEN.** Capture and integrate the same-call thermodynamic source terms and precipitation enthalpy export on the same carrier. A broader model total-energy budget would also need its pressure-work and kinetic-energy terms.
- **Physical acceptance: OPEN.** These results are one-rank/one-tile first-call research evidence, not multi-tile, forecast, or operational validation.

## Evidence and replay

The bounded replay is [pr65_samecall_budget_audit.py](../tools/pr65_samecall_budget_audit.py). It uses a shared active hybrid geometry measure from the existing geometry auditor, binds all three captures to the successful isolated-run receipt, rejects changing geometry, and keeps the hybrid and `DEN*DELZ` measures separate. Its float64-promoted `DEN*DELZ` diagnostic is shown beside the legacy geometry auditor's REAL*4-product value.

The machine-readable results and raw hashes are in [PR65_SAMECALL_WATER_BUDGET_20261007.json](evidence/PR65_SAMECALL_WATER_BUDGET_20261007.json). The exact replay command, raw paths, receipt, executable identity, and source inspection hash are recorded there. No model source or run artifact was modified for this audit.
