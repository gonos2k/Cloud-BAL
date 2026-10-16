# PR87 saved-state host-cutoff regression

This bounded regression checks whether the saved POST_KDM6 pair can be made
unpaired by the native generic host cleanup before a later FogDES call. It
extracts `microphysics_zero_outa` from the hash-pinned WRF source, applies the
current source-generator overlay, and compiles that procedure together with
the exact saved-candidate FogDES helper using the pinned Intel profile at O0
and O2. It does not build or run the WRF model.

The replay uses the first exact OFF/COUPLED matching candidate in
`docs/evidence/pr87_state_cycle_20261016/post_kdm6_cycle.json`:
`QC=8.469214662909508e-9`, `QNC=2021875.875`. The host cutoff is the pinned
`mp_zero_out=2`, `mp_zero_out_thresh=1.e-8` path. In the ordinary call,
`microphysics_zero_outa` zeros the positive subthreshold QC while QNC remains
positive, and the actual FogDES helper raises its paired-moment fatal. With
the optional paired-species argument enabled, QC/QI/QR/QG remain while the
same routine still clamps negative QV and thresholds QS; the saved QC/QNC
pair reaches FogDES. A separate optional-argument omission check confirms a
scalar call still thresholds its small non-QNC field and leaves QNC alone.

This establishes a reproducible source mechanism for the saved state. It does
not establish that native POST_HOST_CLEANUP or FOGDES_INPUT runtime values
match the replay; those observations are in the native run evidence. It also
does not justify skipping the distinct `microphysics_zero_outb` boundary
nonnegativity cleanup. The overlay must keep that safety behavior intact.

Run from the Cloud-BAL root with:

```bash
python tools/pr87_native_cycle_regression.py \
  --output docs/evidence/pr87_native_cycle_20261016/native_cycle_o0_o2.json
```

The JSON records the exact source and compiler identities, compile commands,
O0/O2 outputs, and scratch paths. Compiler output and executables remain in
fresh `/var/tmp/pr87_native_cycle_*` directories.

## Native completed-state audit

`tools/pr87_completed_state_audit.py` independently audits each timestep in a
compressed or raw PR85 state stream. It reuses the PR85 reader, density
contract, paired PSD-cone, entry-cap, and conversion helpers. The CLI requires
the PR87 overlay build receipt, candidate executable, and expected parent
executable hash. The diagnostic stream has one complete six-stage timestep;
the separate cloud-cycle log records the failed consumer entry at timestep 2.

```bash
python tools/pr87_completed_state_audit.py \
  /var/tmp/pr87_diagnostic_OFF_20261016/run/pr85_joint_moment_stages.raw.gz \
  docs/evidence/pr87_native_cycle_20261016/completed_state_audit.json \
  --build-receipt /var/tmp/pr87_cycle_diagnostic_build_20261016_v2/pr87_native_overlay_build.json \
  --expected-executable /var/tmp/pr87_cycle_diagnostic_build_20261016_v2/wrf_pr87_overlay.exe \
  --expected-parent-executable-sha256 9642a471acd39320efca247a55104da9369ef93d8735e60a0d266bf20332b943
```

The attached `runtime_cycle.json` binds the observer log, fatal log, effective
namelist, run receipt, build receipt, and hashes. It also verifies that the
diagnostic's first-call input and KDM6 pre/post readbacks match the frozen PR86
OFF baseline byte hashes.
