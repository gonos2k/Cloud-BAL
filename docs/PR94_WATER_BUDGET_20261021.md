# PR94 frozen C4 absolute water budget

This report accounts for the completed PR93 C4 OFF and COUPLED runs from elapsed 0 to 600 seconds. Each arm is analyzed independently using its receipt-bound WRF history and the native hybrid dry-air carrier from `pr87_native_history.py`:

`dry layer mass = DX*DY/(MAPFAC_MX*MAPFAC_MY) * -(C1H*(MU+MUB)+C2H)*DNW/g`.

The inventory includes QVAPOR, QCLOUD, QICE, QRAIN, QSNOW, and QGRAUP at every 60-second history record. The actual C4 history metadata identifies `RAINC` as “ACCUMULATED TOTAL CUMULUS PRECIPITATION” and `RAINNC` as “ACCUMULATED TOTAL GRID SCALE PRECIPITATION”; both report units `mm`. The public host call maps `RAINNC=grid%rainnc` and `RAINNCV=grid%rainncv` in the archived WRF `solve_em.F` source contract. The KDM6 helper path updates `rainncv` from bottom fall rates in the maintained wrapper source (`module_mp_kdm6.F`, line 1312), and the PR86 public helper budget verifies the same conversion. `RAINNC` is the total grid-scale accumulator; `SNOWNC`, `GRAUPELNC`, and `HAILNC` are phase subsets and are not added a second time. The cumulative increment `Δ(RAINC+RAINNC)` is converted from mm to mass using `1 mm = 1 kg m-2` and the same `DX*DY/(MAPFAC_MX*MAPFAC_MY)` cell area. OFF and COUPLED have exact matching timestamps, DX/DY, mass map factors, latitude/longitude and hybrid vertical coefficients. Precipitation is added after summing atmospheric water changes vertically for each column.

| Arm | Atmospheric water change (kg) | Precipitation increment (kg) | Available signed residual (kg) | Residual L1 by column (kg) | Maximum absolute column residual (kg) |
|---|---:|---:|---:|---:|---:|
| OFF | -13,448,713,801 | 159,736,274,941 | 146,287,561,140 | 1,613,462,180,780 | 711,520,898 |
| COUPLED | -13,352,195,793 | 159,638,965,603 | 146,286,769,810 | 1,613,346,729,766 | 711,239,142 |

Absolute species inventories for each minute, species changes, per-cell inventory-change signed/L1/max diagnostics, and per-column available-residual diagnostics are in [the machine-readable evidence](evidence/pr94_water_budget_20261021/c4_absolute_water_budget.json). These are scope diagnostics, not closure: inventory change alone is not a conservation residual. The signed available residual is about 1.46e11 kg in both arms and cannot be interpreted as a source term until the missing whole-model terms are measured.

The [paired native-column map](evidence/pr94_water_budget_20261021/c4_water_columns_v2.png) shows atmospheric inventory change, accumulated precipitation outflow, and the **available imbalance** `ΔWcolumn + precipitation` for each arm. The numerical columns are stored in a private compressed NPZ at `/var/tmp/pr94_water_columns_20261021_v2/water_columns.npz` (directory mode 0700, file mode 0600); the public JSON records its SHA-256 and path. Arrays are kg per native column and are not a 3D residual. Maxima use zero-based native `(j,i)` indices.

| Arm | Column diagnostic | Signed total (kg) | Column L1 (kg) | Max absolute column (kg) | Maximum location `(j,i)`, lat/lon |
|---|---|---:|---:|---:|---|
| OFF | Atmospheric inventory change | -13,448,713,801 | 1,680,944,033,157 | 875,452,387 | (264,69), 43.6875°N 122.9418°E |
| OFF | Precipitation outflow | 159,736,274,941 | 159,736,274,941 | 300,257,954 | (113,30), 36.6088°N 121.0381°E |
| OFF | Available imbalance | 146,287,561,140 | 1,613,462,180,780 | 711,520,898 | (71,161), 34.7723°N 128.4804°E |
| COUPLED | Atmospheric inventory change | -13,352,195,793 | 1,680,607,593,441 | 875,452,387 | (264,69), 43.6875°N 122.9418°E |
| COUPLED | Precipitation outflow | 159,638,965,603 | 159,638,965,603 | 300,257,954 | (113,30), 36.6088°N 121.0381°E |
| COUPLED | Available imbalance | 146,286,769,810 | 1,613,346,729,766 | 711,239,142 | (71,161), 34.7723°N 128.4804°E |

Per-column absolute p95 values (kg) for inventory change / precipitation / available imbalance are OFF `91,476,221 / 8,441,883 / 86,929,326` and COUPLED `91,452,754 / 8,425,337 / 86,929,262`. The map and maxima describe spatial patterns in available quantities; neither indicates water creation or closure.

The histories contain instantaneous `QFX` (upward surface moisture flux, kg m-2 s-1) and wind fields, plus accumulated surface and phase diagnostics. They do not contain a time-integrated surface water-exchange ledger or water-species lateral/top face fluxes. Winds alone cannot supply species flux. The namelist has an empty `&fdda` block, so analysis nudging is not configured; `specified=.true.` and a 5-cell specified boundary / 4-cell relaxation zone mean lateral boundary exchange is active but no species flux is recorded.

Existing source ledgers do contain selected contributions. The KSAS ledger records QC/QI mass source packets with their paired number source. The PBL ledger records 90 RK-stage tendency correction summaries for four tracked channels. These are partial process terms, not all water tendencies. The grouped joint transport ledger records 90 RK summaries of Q/N candidate/fallback processing and pressure-coordinate rejections; it does not record face water flux. The diffusion ledger records 29 selected paired-scalar correction rows. KDM6 process and numerical budgets are guarded by a first-call-only trace; they do not provide timestep 3–30 process closure. The exact fields and record counts are in the JSON evidence.

The available residual is the signed inventory change plus accumulated precipitation outflow; its column L1 and maximum absolute column value are reported separately. The 3D cell L1 is only the L1 of atmospheric inventory changes, because precipitation is available as a surface column quantity and is not distributed among levels. Missing terms include lateral and top boundary water fluxes; time-integrated surface exchange and precipitation interception or evaporation; non-microphysics water sources and sinks beyond the selected KSAS/PBL captures; numerical transport, diffusion, and roundoff residuals for every water species; and phase-specific precipitation boundary attribution. These terms are unmeasured, not assumed zero. No initial-analysis geometry, C14/C18 terms, or analysis increment is treated as a timed source.

## Per-call geometry check

The receipt-bound C4 KDM6 source declares both `DEN` and `DELZ` as `intent(in)`. The source order is `PRE_KDM6` → `microphysics_driver` → `POST_KDM6` → `after_all_rk_steps`. A separate receipt-bound PRE capture exists at KDM6 timestep 3 (60 seconds) and records the actual input `DEN`, `DELZ`, and all six water fields. Against the same-minute `PH+PHB` output thickness on its 280×39×232 interior support, the PRE `DELZ` comparison has mean absolute difference 0.000358 m, maximum 0.003426 m, mean relative difference 5.68e-7, and maximum relative difference 5.35e-6. The history geometry is emitted after the microphysics and after `after_all_rk_steps`, and it does not exactly reproduce the captured PRE input thickness.

The original PR94 analysis did not calculate a per-call water-plus-precipitation residual. Its geometry probe reads the timestep-3 PRE dump, whose minute-history precipitation increment cannot be assigned to that call. **PR95 correction:** the same closed C4 receipts also contain timestep-1 pre/post and process captures. Their 12 shared state fields match `PRE_KDM6(1)` and `POST_KDM6(1)` bitwise; process-stage-0 DEN/DELZ match that input. The [PR95 same-call account](PR95_CALL_WATER_BUDGET_20261021.md) uses those captures and the actual call bottom flux. Thus the previous claim that only timestep 3 had a receipt-bound DELZ capture was too broad. The original PR94 JSON is preserved as historical evidence; its 0–600-second inventory results and T3-versus-history geometry comparison are unchanged.

## PSD representation audit

The frozen C4 PSD boundary reconstruction is verified against each run receipt and compressed ledger. Across the full ledger, both arms have 8,400 timestep/latitude contexts and every recorded row has native reconstruction available (OFF 10,548 rows; COUPLED 10,543 rows). Species totals are OFF cloud 655, ice 2,925, rain 6,968; COUPLED cloud 655, ice 2,925, rain 6,963. The detailed species/stage/side counts are in the JSON. This measures recorded boundary-event coverage, not every PSD state or every cell processed by KDM6.

The selected ice capture in both arms records the first valid-to-invalid transition at call `[1,1,1]`, covering one transition level. The subsequent stage1 lower-bound reconstruction is at ledger call index 6685: `Nbefore=622.9359741`, `Nnative=Ndirected=622.9367065`, `exactNmin=622.9366863`, and native signed change is `+0.000732421875 # m-3`; there are no boundary rows after the first selected call in that selected capture.

The boundary ledger records Q, dry density, lambda bounds, before/native/directed number, native delta, storage correction, and representability, but not layer thickness or cell volume. Therefore it cannot support a volume-integrated count change. The selected event's signed N change is retained as a local representation diagnostic, not a weighted global count budget. Directed number changes repair or reconstruct a represented PSD state; they do not establish nucleation or physical particle production. The machine-readable output records the ledger identities and this weighting limitation.

The paired C4 summaries cover activity and fixed-support field responses, not a water inventory or closure. This report adds absolute per-arm inventories from the actual 0–600-second histories; it makes no precipitation-suppression, nucleation, or complete conservation claim.

## Provenance and limits

Both run receipts are COMPLETE with return code zero. The analysis verifies the receipt hash, the receipt-bound history file hash, the complete contiguous 11-record history window, and the pinned gravity receipt consumed by the native history reader. The source graph was read before implementation; it was not mutated by this focused change. Graph freshness does not validate runtime physics. No model executable was rebuilt or rerun for this accounting.

The map uses pooled OFF/COUPLED absolute-value p99.5 color limits for each field; tails saturate and colorbar extensions mark them. The JSON records the actual limits, saturated-column counts, and unclipped signed extrema. Numeric NPZ files remain private outside the repository.
