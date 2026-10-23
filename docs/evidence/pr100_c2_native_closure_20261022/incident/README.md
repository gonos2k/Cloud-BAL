# Root working-directory incident appendix

This appendix records a bad-cwd diagnostic launch and its preservation/recovery disposition. It deliberately excludes the approximately 1.487 GB of raw outputs, the diagnostic executable, and large module/object files. The inventories and quarantine receipt pin those preserved artifacts without copying them here.

The bad-H three-transfer diagnostic ran from the KLAPS50 root during 2026-10-22 12:12–12:18 UTC and created 33 top-level raw files. They were archived and atomically quarantined; post-quarantine review verified the receipt-bound contents/inodes and confirmed no top-level `.raw` files remained. The bad-cwd outputs are excluded from scientific interpretation and do not establish a source or physics failure.

The initial concern that the three `status='replace'` outputs might have overwritten prior inodes is resolved for this launch by the pinned Intel profile (`tests/intel_toolchain.sh`, SHA256 `5439fa3a…711b4`) OpenMP/big-endian probe. On this filesystem, replacement retained an existing inode; the three incident output inodes were born during the run, and the recorded bad-launch sequence contains no `rm` or unlink. Thus this launch created the files without truncating a prior inode. The initial review, probe addendum, and post-quarantine review are retained separately under `reviews/`.

Protected KLAPS50/Cloud-BAL source inventory (627 entries), both graph hashes, wiki hashes, and Intel profile hash were rechecked unchanged. Root verified isolated C2 working directories unchanged. Separate guarded C1 HYDRO/COUPLED receipts are included under `guarded_replays/`; they are not results from the incident launch.

`incident_summary.json` binds the evidence hashes, protected-state pins, incident limits, and corrected replace-path conclusion. `SHA256SUMS` covers every file in this bounded appendix. No source or physics failure is claimed.
