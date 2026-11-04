# B1 rain-number prior first-call capture

This archive contains the 20-second instrumented `B1_RAIN_NUMBER_PRIOR` probe's first timestep state. The candidate probe executable SHA-256 is `6706f6162d37c057b2699afd03ae7c0b4dbf94fe97b925c0369916ba6c708661`; the later six-hour fixed forecast executable is distinct (`68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f`). The probe ran with eight MPI ranks on CPUs 56–63. All 89 staged input files remained unchanged.

`capture_manifest.json` inventories compressed stream hashes and byte sizes, source stream hashes and sizes, the eight invocation inventories, the schema, and the run/scan/preflight receipts. The 56 `state_<stage>_rank<rank>.bin.gz` streams use deterministic gzip metadata. They are candidate-only; there is no OLD/FIX arm relabeling. Each CBSP0001 stream uses a 68-byte big-endian header. ENTRY and PRE_UPDATE payload rows cover the actual rank-owned call tile cores in implicit j,k,i order. `state_calls_rank*.txt` gives call and local-memory bounds. Uncalled cells are not filled with zeros.

The first-call check compares every called cell from raw ENTRY to PRE_UPDATE. The captured KDM6 source applies `QR=max(QR,0)` and `NR=max(float32(QNRAIN*DEN),0)` before PRE_UPDATE. Both numeric comparisons and DEN identity match exactly across 2,533,440 cells. Negative raw ENTRY QR/NR values therefore indicate the source's explicit clipping path; they are not interpreted as a negative initialized prior. The actual PRE_UPDATE state has 246,132 rain cells satisfying the source's `QR >= qcrmin` and `NR >= nrmin` PSD guard, no NRMAX exceedances, and 437 reconstructed slopes below the source lambda minimum (which the source then clamps).

`replay_candidate_preflight.py` verifies the archived hashes, decompresses the streams into a temporary directory, uses the retained CBSP reader and initialization validator, repeats the exact ENTRY-to-PRE_UPDATE checks, and compares the resulting metrics with the frozen preflight receipt. Example invocation from the Cloud-BAL repository root:

```bash
python3 docs/evidence/cp02_state_path_20261104/candidate/preflight_capture/replay_candidate_preflight.py \
  --repo-root "$PWD" \
  --candidate-input /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_state_path_20261104/runtime/B1_RAIN_NUMBER_PRIOR_6H/wrfinput_d01 \
  --policy docs/evidence/cp02_state_path_20261104/lineage/B1_RAIN_PSD_PRIOR_POLICY_20261104.json \
  --output /tmp/b1_candidate_preflight_replay.json
```

This capture establishes only the initial KDM6 state and source guards. It is not forecast performance or scientific admission evidence. The six-hour run and the frozen 26-cell CSI evaluation are separate.
