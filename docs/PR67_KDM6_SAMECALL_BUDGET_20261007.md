# PR67 KDM6 Same-Call Budget and Safety Results

**Status: diagnostic complete; both research candidates rejected and disabled.** The observer-only run reproduces the current-source behavior. A source-bound process capture exposed a major ice-sedimentation storage loss; the isolated normalization experiment removes that loss in the sedimentation carrier. The ice-only and combined research candidates both fail the existing 20-second reflectivity safety gate, so neither is suitable for enablement.

## Source and capture

The capture is bound to the retained generated KDM6 source and archived `.F` hostcopy by hash; the generated source preprocesses byte-identically from that `.F` under the retained route. The hostcopy is explicitly identified in [the manifest](evidence/pr67_kdm6_budget_20261007/manifest.json); this is not a claim that an unbound current source was instrumented. The uninstrumented control and observer use separate fresh host archives whose KDM6 members match their selected object files byte-for-byte. External static dependency closure is partial. Builds used pinned Intel `ifx` 2026.0.0 in fresh `/var/tmp/pr67_budget_capture_20261007` trees. The final analyzed streams use `-convert big_endian`; earlier little-endian runs are retained as completed exploratory format variants. The compile logs do not preserve full compiler argv, and no separate HDF5 rebuild attempt was retained; see [build provenance](evidence/pr67_kdm6_budget_20261007/build_provenance.json) for those limits and runtime library records. No maintained WRF source or operational input was changed.

The observer records the public-call state, first ice substep, ice fluxes, bottom phase fall, and accumulation increments at the same active geometry. The parser checks big-endian record structure, stage and header order, call-wide bounds/timestep, positive finite density/thickness, and constant stage-2 `DENR` and optional accumulator flags. It reuses the canonical KDM raw-trace and geometry readers. All three analyzed runs passed their input and output isolation receipts. They share the same 100 non-executable inputs; each receipt separately hashes its variant executable.

The base source already normalizes the ice mass and number channels after the initial slope setup and at earlier refreshes. The uncovered point is the final `slope_kdm6` refresh after the rain minor loop and before first ice use: the base normalizes channels 1–3 and number channel 1 there, but not ice mass channel 4 or ice number channel 2. The source then uses those overwritten speeds as per-layer rates. The research-only delta adds only `work1(:,:,4)/delz` and `workn(:,:,2)/delz` at that post-rain refresh. The exact generated-source delta and hashes are in the evidence directory.

## Same-call water and ice measurements

The tile is 232 × 280 × 39, with 280 process rows and 840 ordered stage records. All variants have the same raw KDM entry and geometry hashes.

| Variant | Six-water change | Mapped bottom precipitation | Focused residual |
|---|---:|---:|---:|
| Observer only | −1,291,131,029,874.30 kg | 498,931,427.55 kg | −1,290,632,098,446.75 kg |
| Ice-only normalization | −492,400,304.75 kg | 498,931,427.55 kg | +6,531,122.80 kg |
| Combined PR61+PR62+PR63+PR67 | −492,401,757.92 kg | 498,931,427.55 kg | +6,529,669.63 kg |

For the combined run, six-water mass changes from `9.298041245598048e13 kg` to `9.297992005422256e13 kg`. The precipitation mass is mapped once from captured bottom phase fall rates using the source equation and active map area. `rainncv` is a cumulative millimeter accumulator; snow/graupel accumulators are subsets and are not added again. The residual is a measured focused diagnostic, **not** a whole-scheme water closure or energy closure.

The first ice substep illustrates why the weight basis matters. With hybrid-pressure dry-mass weights, QI changes from `1.2906362192606e12 kg` to `1.2906385973050e12 kg` in the patched runs, a `+2.378044e6 kg` diagnostic difference. With the captured source-native `DEND × DELZ × area` sedimentation carrier, it changes by only `+104.24 kg`. These carriers differ by at most `9.535e-4` relative per layer. The native carrier is the appropriate local transport measure; neither result alone proves full-call closure or physical growth. In the observer-only run QI falls from `1.2906362192606e12 kg` to `3.618e3 kg` after the first ice substep.

## Safety gate and output crosscheck

At active output time `2026-08-16_12:00:20`, baseline observer output has one nonfinite `REFL_10CM` cell. The ice-only run has 26, and the combined run has 25. The combined run's 25 nonfinite reflectivity cells all coincide with `QRAIN > 0` and `QNRAIN = 0`; none have positive rain number. The ice-only run has the same 25-cell overlap plus one cell with nonpositive rain mass and zero rain number. This is a same-time co-occurrence, not a proven causal explanation.

In the combined first-call KDM6 post-state, positive mass with zero moment counts are QC/NC 1, QI/NI 0, QR/NR 25, and QG/BG 0. The combined WRF output has QCLOUD/QNCLOUD 1, QICE/QNICE 0, QRAIN/QNRAIN 25, and QGRAUP/QIB 0; QNCCN is not treated as a graupel moment. Both research candidates fail the reflectivity safety gate and are rejected. The combined candidate still has 25 reflectivity NaNs.

The KDM6 temperature diagnostic `TH × PII` stays finite. For the combined run it changes in 1,181,094 active cells with maximum absolute change 3.2303 K. This does not override the reflectivity failure or establish a complete thermodynamic budget.

## Evidence and validation

- [Evidence manifest and run receipt bindings](evidence/pr67_kdm6_budget_20261007/manifest.json)
- [Pinned build, selected dependency, HDF5 runtime, and neutrality evidence](evidence/pr67_kdm6_budget_20261007/build_provenance.json)
- [Uninstrumented control versus observer-only byte comparison](evidence/pr67_kdm6_budget_20261007/uninstrumented_observer_neutrality.json)
- [Same-call budget summaries](evidence/pr67_kdm6_budget_20261007/)
- [Output moment and reflectivity crosschecks](evidence/pr67_kdm6_budget_20261007/combined_output_safety.json)
- [Ice-only generated-source delta](evidence/pr67_kdm6_budget_20261007/ice_only_generated_source.patch)
- [Combined generated-source delta](evidence/pr67_kdm6_budget_20261007/combined_generated_source.patch)

`python3 tests/test_pr67_kdm6_process_budget.py` passes 4 focused parser tests, including rejection of a cross-row `DENR` mismatch. `python3 tests/test_pr67_output_safety_crosscheck.py` passes 4 tests for timestamp, KDM header, receipt hash, and symlink rejection. Both tests are registered in `tests/run_python_contract_tests.sh`. The observer, ice-only, and combined summaries were regenerated from their receipt-bound big-endian captures without rerunning WRF. The combined PR61+PR62+PR63+PR67 candidate preserves the separately reviewed patch bytes; no additional behavior change was added for the inherited zero-QC cloud-number transfer. Whole physics closure, full energy closure, and external static dependency closure remain open.
