# PR68 carrier reconciliation (2026-10-07)

## KDM6 same-call residual decomposition

The combined PR67 run's reported focused residual is `+6,529,669.63 kg`:

`R_h = (M_h,post - M_h,pre) + P = -492,401,757.92 + 498,931,427.55 kg`.

Here `M_h` is the PR67 hybrid-pressure dry-air state measure and `P` is the mapped bottom precipitation increment. Replaying the same pre/post water fields with the source-native sedimentation carrier `DEND × DELZ × map_area` gives:

| Term | kg |
|---|---:|
| Native-carrier cellwise state change, float64 subtraction | −497,019,313.399 |
| Same mapped bottom precipitation | +498,931,427.55 |
| Native-carrier cellwise residual | **+1,912,114.152** |
| Hybrid-minus-native cellwise carrier term | **+4,617,555.291** |
| Hybrid global-minus-cell reduction correction | **+0.186** |
| Reported hybrid-carrier residual | **+6,529,669.63** |

The independently accumulated identity is `R_h = R_native,cell + (ΔM_h,cell − ΔM_native,cell) + (ΔM_h,global − ΔM_h,cell)`. Its scalar reconstruction error is checked against a tolerance derived from the scalar operand magnitudes; the check passes. Separately, a direct extended-precision replay computes `Σ[(m_h−m_n)·Δq]` as `+4,617,555.2914 kg`. It differs from the difference of the two independently accumulated carrier deltas by `−0.000675 kg`, within a conservative `28.259 kg` array-summation roundoff bound accounting for all six species reductions. The scalar `8.83e-6 kg` bound and array bound cover arithmetic only; neither estimates physical uncertainty or establishes closure. About 4.62 million kg of the reported residual is the carrier-choice term. About 1.91 million kg remains after that reweighting and is not closed by the available capture. `DEND × DELZ × area` is source-defined for local sedimentation; applying it to all six-water pre/post fields is a diagnostic comparison, not proof that it is the correct all-call extensive measure.

The captured native carrier and hybrid dry-mass measure differ by at most `9.534995e-4` relative per layer. The PR67 raw water fields are float32, so subtracting them before promotion rounds each difference. The updated replay first promotes both snapshots to float64, then subtracts. It reports the legacy float32 subtraction effect separately: `+130.840 kg` on the hybrid measure and `+130.934 kg` on the native measure. The corrected hybrid global-minus-cell reduction correction is `+0.186 kg`; the native correction is `+0.008 kg`. Thus the earlier roughly `−131 kg` hybrid discrepancy mostly reflected float32 subtraction, not only summation of large totals.

The remaining `+1.912 million kg` is an unresolved remainder. The capture does not separate internal vapor/cloud/rain/snow/graupel transfers, single-precision tendency and update rounding, nonnegative clipping, or all substep boundary/storage terms. The available process stream does not contain each transfer's before/after value at every operator, so no one of these terms is claimed as the explanation.

The capture is one public KDM6 call, timestep 1, with `DTCLD=20 s`, active tile `i=2..233, j=2..281, k=1..39`, 280 row groups, and 840 ordered process records. Capture bytes and the run executable are checked against the successful isolated-run receipt. All 101 declared run inputs have valid matching before/after receipt hashes, unique paths within the run root, and current file bytes that rehash to the receipt values. This verifies the preserved input inventory, not full runtime process closure. The selected combined generated source (`9efc0925…`), KDM6 object (`e846c95d…`), and executable (`517a4813…`) are checked against the immutable PR67 combined-variant manifest and build-provenance record; selected source and object bytes also match their recorded identities. The run-local `runtime_reference_manifest.json` is retained as an auxiliary control-variant reference. Its observer source/object/executable hashes do not identify the selected combined variant; its executable hash does not match the receipt-bound executable. It is not used as build lineage. Full host object/dependency closure and captured expanded compiler argv remain partial. The scoped support claim is limited to the receipt-bound capture and numerical reconciliation.

## PBL matrix and tendency equation

The selected Shinhong path receives `P8W` as `P3DI` and forms total interface thickness `DEL_k = P8W_k - P8W_(k+1)`. Its transport coefficients use `dt2/DEL` and total-pressure layer differences. The dry layer pressure measure linked for the PR67 selected cell is `dp_d,k = -(C1H_k*MUT + C2H_k)*DNW_k`; the dry mass weight is `m_d,k = area_k*dp_d,k/g`. For this capture the live `MUT` and vertical coordinates were recorded, but hybrid coefficients are linked to the immutable `wrfinput_d01` because the retained `module_domain` layout did not pass the grid-id/DX sanity check. This is a provisional, statically linked dry measure.

For a fixed cloud-water call with the closed (`ic=2`) lower donor and no source vector, write the captured implicit tridiagonal solve as `A_t q_new = q_old`. Dry-carrier conservation requires `m_d^T(q_new-q_old)=0` for every admissible `q_old`, which is equivalent to `A_t^{-T}m_d=m_d`. That criterion applies to the complete matrix and its right-hand side. Replacing only `DEL` in one line would leave the pressure-gradient conductance, adjacent-layer terms, endpoint handling, and boundary forcing on inconsistent measures. The captured same-matrix float64 check gives `max|A_t^{-T}m_d-m_d|=220,057.70 kg` (`8.77e-7` of dry column mass); this is small but not zero and is not a closure pass.

For vapor, the source adds the bottom RHS term `s_sfc,1 = qfx*g*dt2/DEL_1`. The carrier-weighted response is `m_d^T A_t^{-1}s_sfc`; it must be accounted for as the surface input, with the source's `AREA2D` convention reconciled to physical mapped area. The QC solve has no such surface vapor term, and its closed lower donor remains part of the matrix equation rather than a source. The returned pre-settling cloud-water tendency is a distinct check: compare `dt2 * Σ_k(m_d,k * rqc_pbl,k)` with `Σ_k(m_d,k * (q_new,k-q_old,k))`, while keeping the measured `0.0029 kg` difference explicit.

The driver adds the separate `bl_fogdes` settling tendency after Shinhong. Its contribution is `dtbl * Σ_k(m_d,k * rqc_fog,k)` and belongs in the full driver budget as its own term, not in the matrix residual. In this capture it is `164.80 kg s⁻¹` as a weighted tendency. A future native fix should first capture or fully link the dry coefficients and source/boundary terms, then change and validate the whole matrix and RHS together. No PBL code is changed in this PR68 audit.

## Artifacts and verification

- Replay implementation: [`tools/pr68_carrier_budget_replay.py`](../tools/pr68_carrier_budget_replay.py)
- Focused numerical contract: [`tests/test_pr68_carrier_budget_replay.py`](../tests/test_pr68_carrier_budget_replay.py)
- Machine-readable result and artifact hashes: [`combined_decomposition.json`](evidence/pr68_carrier_20261007/combined_decomposition.json)
- Immutable selected-variant source manifest and build record: [`manifest.json`](evidence/pr67_kdm6_budget_20261007/manifest.json), [`build_provenance.json`](evidence/pr67_kdm6_budget_20261007/build_provenance.json)
- Upstream same-call capture context: [PR67 KDM6 budget](PR67_KDM6_SAMECALL_BUDGET_20261007.md) and [PR67 PBL carrier audit](PR67_PBL_SAMECALL_CARRIER_20261007.md)

`python3 tests/test_pr68_carrier_budget_replay.py` passes focused cases, including mismatched time/bounds, changed carrier values, mutated receipt-bound captures/executables, and rejection of a control-variant source hash for the combined capture. `python3 tools/pr68_carrier_budget_replay.py ... --source /var/tmp/pr67_budget_capture_20261007/source/module_mp_kdm6_combined_research.f90 --manifest docs/evidence/pr67_kdm6_budget_20261007/manifest.json` replays the immutable combined capture without rerunning WRF. Neither the algebraic replay nor graph freshness establishes scientific closure.
