# PR67 same-call PBL carrier audit (2026-10-07)

## Result

This observer run captures the PBL driver's actual `MUT`, `P8W`, `ZNW`, and `ZNU` arguments before the selected Shinhong call, then captures the returned cloud-water tendency before and after the separate fog-settling call. The selected invocation is `(i,j)=(172,76)`, `itimestep=1`, `k=1..39`, with `dtbl=20 s` and Shinhong `dt2=40 s`.

The live runtime carrier is directly captured. Hybrid coefficients are **STATIC_INPUT_LINKED** to the immutable `wrfinput_d01` hash because the retained host archive's `module_domain` type layout failed grid-id/DX sanity checks. No live `head_grid` coefficient values enter the audit. Runtime `MUT` matches input `MU+MUB` exactly at the selected cell, and runtime `ZNW/ZNU` match the same input vertical coordinates. This is a source-linked quantitative audit, not a literal same-call coefficient capture.

The source equations distinguish two pressure measures:

- Shinhong receives `P8W` as `P3DI`; it forms `DEL(k)=P3DI(k)-P3DI(k+1)`. The captured `DEL` matches the same-call total `P8W` interface difference exactly. This is the total moist/interface measure used in the transport matrix.
- The dry layer pressure weight is `dp_d(k)=-(C1H(k)*MUT+C2H(k))*DNW(k)`. An independent hybrid-interface check uses `p_d(k)=C3F(k)*MUT+C4F(k)+P_TOP`, whose layer differences match the `C1H/C2H/DNW` calculation within `0.0025 Pa`.

For this call, total `DEL` exceeds the linked dry layer pressure by up to `60.60 Pa` (`1.86%` relative). The same captured matrix has a float64 dry left residual `max|A^-T m_d - m_d| = 220,058 kg`, or `8.77e-7` of the dry column mass. The DEL-weighted residual for that same matrix is `984.8 kg`, or `3.89e-9` of the DEL-weighted column mass. These are measured on the same matrix; the float64 adjoint solve is independent of the native binary32 tridiagonal solve.

The active source branch computes the PBL `AREA2D` argument as `DX*DY` (`25,000,000 m²`); a map-factor expression is present under `#if 0`. The physical dry column budget here uses `DX*DY/(MAPFAC_MX*MAPFAC_MY)` (`25,929,625 m²`) and is kept distinct from the PBL argument area. The runtime PBL call supplies `G=9.81 m s-2`, `DX=DY=5,000 m`, and `AREA2D=25,000,000 m²`.

## Returned tendencies and source separation

The captured Shinhong cloud-water solve changes the dry-mass-weighted column by `28.612 kg`. The returned pre-settling PBL tendency integrates to `28.615 kg` over `dt2`; the difference is `0.0029 kg`. The driver then adds the `bl_fogdes` settling tendency. The capture measures a separate `164.80 kg s-1` weighted settling increment. That increment is not part of the Shinhong matrix result.

For the paired NC path, the same matrix replay changes the weighted column by `-95.055 billion number`; the captured native returned tendency integrated over `dt2` is `-94.579 billion number`. The observed difference is `+0.476 billion number`, about `0.50%` of the signed net change and `8.54e-9` of the gross absolute layer change. The existing PR65 check confirms native NC tendencies equal the source-arithmetic same-matrix replay level by level. The weighted integral discrepancy remains explicit and is not treated as a closure pass.

The closed cloud-water (`ic=2`) solve has no surface vapor-flux term: its bottom donor is initialized directly from `qx`, and the captured tridiagonal endpoints are closed. Fog settling is added afterward. This scope does not establish the full physical input gate, which remains **OPEN**.

## Provenance and limits

The observer changes no physics calculation. The driver source is a small patch against the retained PR65 generated source; the build uses the pinned Intel profile and a fresh `/var/tmp/pr67_pbl_carrier_20261007` scratch tree. The linked archive reuses the retained PR65 host objects and replaces only `module_pbl_driver.o`; this is not a full WRF rebuild. Source, object, archive, executable, and profile hashes are recorded, but the exact expanded compiler argv was not retained (the manifest labels its command as a reconstructed recipe), so these identities are not a full compiler-process attestation. The compile log is empty, consistent with a successful quiet compile. The guarded run receipt is PASS/PASS with return code 0, and it records the unchanged `wrfinput_d01`, the exact local run executable, and single-link raw outputs.

The existing PR65 baseline and PR67 observer runs have byte-identical `wrfout_d01_2026-08-16_12:00:00` files and byte-identical `pr65_pbl_operator.raw` captures. This is a history-neutrality check on the selected run, not full host-closure validation. The focused Python tests pass 3/3, including a nonuniform dense-reference transpose solve, reordered QC-level rejection, and nonfinite QC-rate rejection; the PR65 replay validator also passes on the PR67 run's operator and NC records.

The retained module/domain metadata mismatch is why live hybrid coefficients are not claimed as captured. Static coefficient linkage, coordinate agreement, and `MUT=MU+MUB` agreement support this focused measurement but do not replace full host-closure validation or close the broader physical input gate.

## Artifacts

- [Machine-readable audit](evidence/pr67_pbl_samecall_carrier_20261007.json)
- [Build and run manifest](evidence/pr67_pbl_build_run_manifest_20261007.json)
- [Observer source patch](evidence/pr67_pbl_samecall_carrier_observer.patch)
- [Audit tool](../tools/pr67_pbl_carrier_audit.py)
- [Focused transpose-solve test](../tests/test_pr67_pbl_carrier_audit.py)

The first direct `head_grid` observer run segfaulted before the PBL call. That run and the subsequent metadata-diagnostic attempt remain preserved under `/var/tmp/pr67_pbl_carrier_20261007/`; neither is included as a passing measurement.
