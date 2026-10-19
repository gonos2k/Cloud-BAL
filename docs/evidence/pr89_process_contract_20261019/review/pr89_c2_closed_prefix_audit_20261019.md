# PR89 C2 closed-prefix independent audit

Both 120-second runs closed `INCOMPLETE` after timestep 1 completed (20 seconds) and timestep 2 reached `PRE_RK` before abort. The same failed trial appears in both arms at species/pair index 2, i=233, j=104, k=7. Neither run reaches its six-step request. The strict source-state auditor, bound to the C2 build receipt and candidate executable, reports timestep 1 PASS and timestep 2 INCOMPLETE in both arms.

The binary/source/input bindings check out: both runs execute C2 SHA `4cc58c7261b203bd2dad70a230536292278bc69ff4c18381923e159aaeab0ade`; run inputs are unchanged; each has 101 input files, 120 seconds at 20 seconds per step, and six expected steps. OFF and COUPLED inputs differ only in `wrfinput_d01`. The Intel partial overlay build is PASS_OVERLAY_BUILD, `full_clean_build=false`; `module_em` is the C2 source and KDM6 is the reviewed C1 source.

This is recorded as an **own C2 regression**, not an unexplained host-state or physical failure. Root's source replay identifies Q≈4.6395e-47 and N≈1.315477e-37: the pair is valid under the legacy PSD contract, but its Q rounds to zero at storage. C2's new inactive-ice route intercepts that legacy-valid pair before the old flow. C3 should keep legacy-valid pairs on the original flow, and use the exact-storage inactive path only when legacy validation rejects and the native inactive condition applies.

Machine-readable detail and hashes: `/var/tmp/pr89_c2_closed_prefix_audit_20261019.json` (SHA-256 `c9d3ec6beb7d323c722f928bc19c3d00600fac00dbb55b6226967dc53806cd0d`). No model/source changes or additional native runs were made for this audit.
