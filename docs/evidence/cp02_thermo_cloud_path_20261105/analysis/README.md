# Two-hour selected-cell analysis

The full actual trace receipt has status `PASS_FULL_CAPTURE`, SHA256 `e41105c152b55991784f1fcf0b8c8e1c75fe03fc3d33160b897160adadd33245`; its bound per-file manifest has SHA256 `71a9b13753244693fd543587a81695c14c1ad019a5972948005a44e155df7c8d`. The capture includes 360 steps, 39 mass levels and 123 deduplicated native cells in each arm. Both arms passed mandatory stage and sedimentation substep coverage, wrapper/inner conversions, source-order REAL32 update checks and 246 exact cumulative RAINNC history-word comparisons each. RAINC is a separate cumulus component and is not part of the KDM6 surface return.

`point_stage_recount.csv`, `cloud_rate_recount.csv`, and `rain_presence_recount.csv` include every one of the 39 points. All values are DM065 minus B1 except the explicitly per-arm rows in `rain_presence_recount.csv`. Their scripts verify the full receipt and the part manifests, then reconstruct the required arrays from the lossless `*_parts` directories. No sibling runtime array is needed.

All point values are bilinear weights over native corners. Stages are sampled within a model step; step-end labels use 20 seconds per step. The earliest recorded nonzero is a numerical observation, including very small values; it does not establish a causal onset. The entry, main post-update and wrapper-return rain samples are separate. The wrapper NR is per unit model-air mass and internal post-update NR is per unit volume. A snapshot with zero rain at +1 hour does not imply that earlier sampled rain was always zero.

Within each step, sedimentation and the conditional surface calculation occur before the main limited process-rate update. Post-update to pre-condensation and post-condensation to wrapper return are separately reported as unassigned net gaps. Between-call differences include all intervening model changes and must not be labeled pure transport. The TH/Exner terms are an algebraic decomposition, not a physical energy or causal attribution. Native-cell rain cleanup is applied per corner using `qcrmin=1.e-9` kg/kg; a bilinear value below that threshold does not establish whether every corner is below it. Conditional phases absent from any corner remain missing rather than being set to zero. Fixed Eulerian locations are not trajectories.

The per-arm point arrays use axes `(step, level, point, field)` with 360 steps, 39 levels and the `point_ids` order in the full receipt. Wrapper `entry` and `return` fields are `TH, QV, QC, QR, QI, QS, QG, NN, NC, NI, NR, BG, DEN, TK, P, PII`; water mixing ratios are kg/kg, wrapper number concentrations are per kg of model air, temperature is K and pressure Pa. `phase_N` fields use the exact ordered names in `native/schema/cp04_schema.json`; internal number fields are per cubic metre. `sedimentation_net` has QR, QS and QG increments in kg/kg. `surface_return` contains RAINNC increment and cumulative RAINNC in mm, then snow fraction. `surface_conditional` is indexed pre/post, step, point and source field; NaN means at least one contributing conditional corner is absent.

The paired NPZ uses `_difference` names and DM065 minus B1. `within_call_difference` is return difference minus entry difference. `between_call_difference` is next entry difference minus previous return difference and has 359 steps; its first row bridges return step 1 and entry step 2. `between_theta`, `between_exner` and `between_product_roundoff` provide the corresponding temperature algebra. `prevp_q` is the signed vapor component of rain evaporation in kg/kg per call; its residual includes all other terms and rounding. Condensation and latent temperature-change fields are directly bracketed within-call increments in kg/kg and K respectively, and the two `gap_...` pairs are unassigned vapor and temperature net changes. Per-arm `sedimentation_mstep` retains the four individual corner substep counts rather than a weighted mean. No time-zero sample is manufactured.

To replay the recounts in a checkout, run the following commands from the repository root. They refuse to overwrite existing outputs; use a fresh relocated copy of the evidence directory for a byte-for-byte replay.

```sh
python docs/evidence/cp02_thermo_cloud_path_20261105/analysis/recount_paths.py
python docs/evidence/cp02_thermo_cloud_path_20261105/analysis/recount_cloud_rates.py
python docs/evidence/cp02_thermo_cloud_path_20261105/analysis/recount_rain_presence.py
python docs/evidence/cp02_thermo_cloud_path_20261105/analysis/recount_hour1_boundary.py
```

Each original logical NPZ maps to `<stem>_parts/<stem>.parts.json`; the five manifest hashes and complete reconstruction proof are in `../validation/array_parts_review.json`. `portable_arrays.py` validates those hashes and uses `tools/pack_cp02_selected_npz.py` to verify all parts while retaining only the requested arrays. The +1 h wrapper comparison reads `hour1_native_history.npz`, a 39-level, 123-corner QRAIN/QNRAIN extract of the prior histories. Its receipt pins the original histories and extraction source; recreating that extract, rather than replaying the recount, requires those external NetCDF files. The original pre-portability scripts are retained in `../attempts/portability` because the historical point-stage receipt binds the original script hash.

Native array columns follow `full_capture_receipt.json` → `native_cells_i_j_1based`; map corners by their `(i, j)` coordinates, since global-corner label suffixes and CSV row order are not array indices.

The original full CP04 analyzer also verifies exact recorded runtime and launch
paths as part of its source and history gates. Replaying that full analyzer
therefore requires the original research runtime at those paths. The packaged
array recounts and figures described above are portable and do not relax those
gates.
