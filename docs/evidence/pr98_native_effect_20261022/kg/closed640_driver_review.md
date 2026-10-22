# PR98 closed-640 KG driver peer review — 2026-10-22

## Decision

**GO for the second-phase KG driver, subject to refreshing its public package metadata before publication.** The driver is a narrow wrapper around the already reviewed helper. It binds the first PR98 receipt and helper, pins the second-phase helper hash, validates the frozen first-phase worktree, and overrides only the intended follow-up run state, snapshot count/name/output path, and current graph pins. I did not run `--apply` or update a graph.

The current public first-phase `README.md` and `SHA256SUMS` still describe the earlier helper hash `d3e54ce…`; the current helper file is `92ca3f6…` because it now exposes the dated-snapshot count as a parameter. The driver pins that current helper. Refresh those package hashes/README metadata when assembling the final public package; this is a publication metadata item, not a driver logic blocker.

## Source and driver pins

- `docs/evidence/pr98_native_effect_20261022/kg/update_closed_kg.py`
  SHA-256: `651c5fede18a8bf565c59b8788c6755e7491db7374eb80fbf5a04b77f822e626`
- `docs/evidence/pr98_native_effect_20261022/kg/update_kg.py`
  SHA-256: `92ca3f6aa630807dfde2e7fbb1559b87a1ba0d3f746e211a993be963be01d685`
- Frozen first-phase helper pinned by the driver:
  SHA-256: `d3e54ce6929b9e8fa0857e2a63a2cf4c595b642f5c09173d6956e1925b9733d2`
- Immutable first-phase receipt pinned by the driver:
  SHA-256: `ce651957174ff90cf9ea104fafc9e407fa39590c6825d29ca3910ccf640eaf4d`
- Frozen source worktree: commit `4d0baf151cd2669437f0341307c095fa95fb92e5`; it is clean. Comparing helper source against that frozen worktree shows the only base-helper change is extracting the literal snapshot count `106` into `EXPECTED_DATED_SNAPSHOTS`.

## Configuration and evidence checks

- Executed only the driver's in-memory `engine()` setup, not preflight/apply. It loaded successfully and resolved the expected base, helper/receipt pins, new snapshot `2026-10-22-pr98-closed640`, output path, and audit-state string.
- The driver sets `EXPECTED_DATED_SNAPSHOTS = 108` for this second update. The current inventory is 52 dated snapshots in KLAPS50 plus 56 in Cloud-BAL; the new target snapshot is absent in both. The new output path does not exist.
- The inherited receipt reports 627 maintained-source entries with SHA-256 `0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f`. The driver supplies the first receipt as `PRIOR`, preserving the base helper's maintained-source and immutable-pin gates. I independently ran its immutable pin verifier: all 197 pins pass.
- Current graph hashes match the first receipt pins: KLAPS50 `c3c625c9924c47816bef84e221f4a18ebc53f0459fa3992cf71ce61e4f8d540b`; Cloud-BAL `8706153d4c22aeb7f45c543ebc5b6b6b4eae060af3d34d0ba55770de4825a3a6`.
- The three closed run receipts independently report `INCOMPLETE`, return code 1, and 31 completed steps ending at `2026-08-16_13:10:20` (620 seconds). Receipt SHA-256 values: OFF `bc7561456802326a766420e1d0668613734cc32008deb7dd24dee5e697459aeb`; HYDRO `9e43e1742083a0ace9cc85d8aa5715bdcda782c199135e1c6698262f89c46832`; COUPLED `95079d21b1b08cdaa74d63bf52c73c561f1cf0f16153f3919d31a9f1f64fb87e`.
- The closed audit collection records auditor return code 1 for each arm and no audit artifact, consistent with the driver's generic `FAIL` state. The configured state retains physical approval `FAIL_OPEN` and observation skill `NOT_EVALUATED`; it does not describe the runs as complete or claim scientific approval.

## Scope

No graph update or apply was run. This review checks the second-phase driver's source binding and configuration only; graph output, publication metadata, and runtime/scientific conclusions remain subject to the driver's preflight/apply gates and the existing closed-run evidence.
