# Covered snapshot science diagnostics

These are read-only diagnostics, not a candidate, initializer, new application mask, or confidence policy. The original analysis-selected mask has 294,792 cells; 6,047 were not captured. The whole application stops before the common routine. Only the 288,745 captured selected cells were evaluated for diagnosis; missing cells remain NaN and are never filled from history.

On those same covered cells, captured QI/QS/NI differ in 44,881/2,073/0 stored words from history. Captured background has 226,663 cells with pair-and-mass support and 28,080 of these exceed the rounded NI density cap; those are descriptive prechecks, not full transaction results. The corresponding history counts are 181,233 and 20,078. Positive captured pairs span a wide range: the median analysis-to-background mass ratio is 2.026 and the 99th percentile is about 2.50e8; this ratio is descriptive, not confidence or a cutoff. See `snapshot_diagnostic.json` for definitions and distributions. Analysis-file REAL32 density is used in the cap calculation, not captured DEN.

The unmodified Intel-compiled common routine reports 198,582 accepted and 90,163 failed among the covered diagnostic cells. The diagnostic bulk call fails first at Fortran (i,j,k) = (150,228,11), status header `[-10,150,228,11,2]`. Independent NumPy checks match the covered acceptance/rejection classification and accepted REAL32 output bits. This does not validate the whole frozen application, a first model use, or scientific suitability. Source, input, compiler, binary and output hashes are recorded in `common_receipt.json`; both driver binaries match the earlier audited build. The fresh work directory held all compilation outputs. Clock was inferred from step arithmetic, not read at the breakpoint, and independent NI scalar-base identity and density basis remain unverified. Snapshot labels rely on the stated source/ABI interpretation; receipt validation alone does not independently establish provenance.

## Reproduce

The original large inputs remain in scratch. Paths below correspond to the recorded host; use exact inputs identified by SHA-256 in the receipts. Python requires NumPy and netCDF4. Start in the Cloud-BAL source root and choose a **nonexistent** external scratch path for the common replay. This compiles only through the pinned IFX 2026 profile; it does not run WRF.

```bash
ROOT=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50
SRC="$ROOT/scratch/first_call_water_budget_20261112/Cloud-BAL"
BATCH="$ROOT/scratch/coherent_ice_prior_20261113"
SCI="$SRC/docs/evidence/coherent_ice_prior_20261113/science"
FROZEN="$SRC/docs/evidence/prior_cycle_application_20261112/frozen_application"
python "$SCI/analyze_snapshot.py" \
  --snapshot "$BATCH/assembled/snapshot.npz" --receipt "$BATCH/assembled/receipt.json" \
  --analysis "$ROOT/scratch/physical_moment_handoff_20261110/native_probe_20261110/preflight_v3/wrfinput_d01" \
  --history "$ROOT/scratch/actual_prior_first_use_20261112/prior_forecast/run/wrfout_d01_2026-08-16_12:00:00" \
  --mask "$FROZEN/mask.npz" --policy "$FROZEN/policy.json" \
  --out "$BATCH/snapshot_diagnostic_reproduction.json"
python "$SCI/evaluate_common.py" --repo-root "$SRC" \
  --snapshot "$BATCH/assembled/snapshot.npz" --snapshot-receipt "$BATCH/assembled/receipt.json" \
  --work-root "$BATCH/common_diagnostic_reproduction"
```

The reproduction receipt records the current helper paths, so its hashes of the scripts bind to the published copies. `analyze_snapshot.py` verifies the snapshot receipt binding and baseline history hash, the frozen mask against the analysis, and coverage count. `evaluate_common.py` additionally verifies the original stream, policy, frozen mask, audited source identities and pinned toolchain; it compares common-routine acceptance/rejection classification and accepted values against independently calculated REAL32 results, and verifies unchanged inputs. The calculated outputs are diagnostic artifacts and must not be used as WRF inputs. Reproduction does not remedy the provenance and physical-validation limits above.
