# Independent first-call column ledger

This is the first KDM6 wrapper call from the CONTROL run, rank 3, row j=72, i=118:233, k=1:39. It is not the historical B1 executable and does not establish its budget. The capture has 4,524 entry/return pairs; see `../native/receipt.json` for bounds, executable/source identity, and the scoped 80-second history parity check. Source SHA-256 is `f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595`, executable SHA-256 is `3a286f6691fa94c2dccf55b14e4cbf609b8c9540c2caf83556969932ca9854ea`, and capture SHA-256 is `aa08c30cd371fee2fb01c261f6534176ce1003107d666a644d0a7097d5282f22`.

Reproduce the independent numerical ledger from the project root:

```sh
python3 docs/evidence/first_call_water_budget_20261112/science/independent_column_ledger.py \
  docs/evidence/first_call_water_budget_20261112/native/capturedsmallrecords/rank3.jsonl.gz > /tmp/column_ledger.json
cmp /tmp/column_ledger.json docs/evidence/first_call_water_budget_20261112/science/column_ledger.json
```

The helper checks each binary32 hex value against its decoded decimal, unique entry/return records, unchanged density, thickness and water density, complete levels and consistent surface fields. It sums in binary64. It reports actual captured values, not a reconstruction of internal process terms.

For each column define `W = Σk DEN(k) DELZ(k) [QV+QC+QI+QR+QS+QG](k)` in kg m⁻². The wrapper ledger is `R = W_return − W_entry + DENR/1000 * RAINNCV`, with RAINNCV in mm. RAINNCV is the total precipitation; SNOWNCV includes snow and ice and GRAUPELNCV is a graupel subset, so neither is added to the total. The source first resets RAINNCV for this call. A nonzero R contains numerical rounding and all nonconservative terms, including entry clipping, final threshold cleanup, and any imbalance in other processes; these must be measured separately before assigning a cause. Interior physical phase redistribution changes individual species but ideally cancels in the six-species sum.

For one sediment substep, the target computes each donor's outgoing mass once, caps it by donor inventory, and uses that same mass as the receiving layer's incoming transfer. The actual top inflow is zero (`sed_mass(kte+1)=0`); the actual surface export is `sed_mass(kts)` summed over the executed substeps and species. In the source `falk = real(sed_mass/(dtcld*DELZ))`; accumulated `fall` and the precipitation diagnostic can have additional binary32 rounding, so the diagnostic and the actual transfer are not interchangeable at bit precision. Phases 9/10 bracket rain/snow/graupel sedimentation, with phase 18 giving outgoing/incoming mass; phases 20/21 bracket ice, with phase 22 giving its transfer. The full-column stage capture must check those boundaries and report entry clips and threshold cleanup separately. The wrapper ledger alone cannot identify these terms or prove that the residual is rounding.

| Quantity | Column (192,72) | Column (201,72) |
|---|---:|---:|
| ΔQV, kg m⁻² | +0.835327500 | +1.310870809 |
| ΔQC, kg m⁻² | −1.976083296 | −2.983572166 |
| ΔQI, kg m⁻² | −14.978115572 | −13.095896423 |
| ΔQR, kg m⁻² | −0.000780713 | +0.093294552 |
| ΔQS, kg m⁻² | +16.118347952 | +14.657643278 |
| ΔQG, kg m⁻² | +0.000789533 | +0.017216334 |
| Total precipitation, kg m⁻² | 0.000514157 | 0.000540681 |
| Residual R, kg m⁻² | −0.000000439 | +0.000097064 |

Column 201 has the largest absolute residual in the 116 captured columns. At (192,72,28), the largest captured local total-water decrease, entry QI is 0.004470638 kg/kg and return QI is zero; QS changes from zero to 0.004174439 kg/kg. QV changes from 0.00006318093 to 0.00006173829 kg/kg. Entry temperature calculated as TH×PII is approximately 216.5414 K, pressure is 16991.41 Pa, and NI is zero. The local total-water decrease is about 0.297642 g/kg. It does not by itself measure column loss: sediment transfer and phase conversion can move water between levels and species. This captured CONTROL case must not be conflated with the separately observed historical B1 change.

Evaluating the source's ice-saturation formula in binary64 from the captured entry temperature, pressure and constants gives QSI ≈ 0.0000596413 kg/kg and relative humidity with respect to ice ≈ 1.05935. This is an approximate wrapper-input diagnostic, not a recorded internal model value.

The source has a cold-ice-to-snow transfer when computed ice mean diameter reaches 200 μm, and warm ice transfers to cloud water. Both change phase category rather than directly removing total water. Initial NI is zero in the highlighted cell; a credible physical change requires an independently justified number prior or process basis and evaluation under observed incoming thermodynamic conditions. The ledger does not justify an arbitrary QI-to-QS conversion, a global parameter change, or a new cap-driven redistribution.

## Independent replay stage check

The pinned-source full-row O2 replay matches every captured native terminal word for 21 three-dimensional and eight two-dimensional fields, and the instrumented replay matches the uninstrumented replay. The O0 comparison also matches; see `../replay/results/O0_comparison.json` and `O2_comparison.json` for scope. This is a first-call reproducibility check, not validation of the model's physical realism. The stage trace SHA-256 is `0927b8ee126b6f6c1afc948aac5725c6d99648530c66abe6a8e54668600b617c`.

```sh
python3 docs/evidence/first_call_water_budget_20261112/science/independent_sediment_ledger.py \
  docs/evidence/first_call_water_budget_20261112/native/capturedsmallrecords/rank3.jsonl.gz \
  docs/evidence/first_call_water_budget_20261112/replay/results/cp04_t000001-000003_rank3.bin > /tmp/sediment_ledger.json
cmp /tmp/sediment_ledger.json docs/evidence/first_call_water_budget_20261112/science/sediment_ledger.json
```

The stage check verifies zero top inflow and exact identity of outgoing and incoming transfers on each interior face in each captured sediment substep, for both columns and all four falling species. It separately calculates stage 1→2 entry clipping and stage 32→33 threshold cleanup from all six species. For each species, its sediment residual is its observed storage change plus actual bottom outflow; it includes the effect of storing updated mixing ratios as binary32. Units in the following decomposition are kg m⁻². `Other` is the remaining imbalance in all other processes and their numerical rounding; it is not assumed to be a single identified process.

| Component of wrapper residual R | (192,72) | (201,72) |
|---|---:|---:|
| Entry clipping | +6.55316e−8 | +9.61440e−5 |
| Threshold cleanup | −1.97044e−7 | −1.36033e−7 |
| Sedimentation storage rounding residual | −1.93335e−7 | −4.58509e−8 |
| Diagnostic precipitation minus actual bottom transfer | +6.04400e−11 | +9.61225e−12 |
| Other process and rounding residual | −1.14071e−7 | +1.10172e−6 |
| **R** | **−4.38858e−7** | **+9.70638e−5** |

For column 192, actual bottom outflow is 0.0005141566485 kg m⁻², entirely rain to displayed precision, compared with diagnostic total precipitation 0.0005141567090 kg m⁻². Column 201's large wrapper residual is dominated by positive entry clipping; the stage audit does not establish why the input contains negative hydrometeors or whether that clipping is physically appropriate. Column 192's near-closure and its net snow increase do not alone identify the individual mechanisms converting or transporting its ice.

`stage_telescope.csv` and the `telescopes` array in `sediment_ledger.json` give all six species for two 39-layer columns at each observed boundary. They use the exact CP04 phase definitions in `../replay/results/cp04_schema.json`; the capture's one RSG and one ice substep are checked explicitly. The stages are wrapper entry → phase 1 raw → phase 2 clipped → phase 9 RSG pre → phase 10 RSG post → phase 20 ice pre/phase 21 ice post → phase 6 main-update pre → phase 8 main-update post → phase 32 pre-cleanup → phase 33 post-cleanup → phase 34 loop end → wrapper return. Phase 20/21 contain QI but not the other five species; source inspection establishes that the ice sedimentation loop leaves those five unchanged, and the script verifies that QI entering phase 20 equals QI leaving phase 10. Source phases 18/22 supply the REAL64 interface transfers. The remaining broad intervals retain all included operations rather than assigning their changes to an unobserved individual branch.

For column 192 the phase 8→32 interval changes QI by −15.432820745 and QS by +15.432820750 kg m⁻², while six-species total changes by −5.83749e−7 kg m⁻². The interval contains the source's cold ice diameter reclassification and other operations. At the highlighted level 28, phase 8 QI is 0.004073088057, QS is 0.000101350830 kg/kg and NI is 489499.375 m⁻³; phase 32 has QI zero, QS 0.004174438771 kg/kg and NI zero. Those values match the intervening source transfer of QI to QS, but entry NI=0 does not determine the NI at the later branch. No independent evidence here selects a new number prior or redistribution policy.
