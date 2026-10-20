# PR91 C8 source-store contract review

## Identity and method

This read-only review compared `tools/pr91_source_store_contract.py` and its focused tests against the emitted C8 candidate host source:

- Pinned input `_i` source: `/var/tmp/pr91_native_build_d3_20261020/source/overrides/module_em.F`, SHA-256 `dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d`.
- Emitted C8 source: `/var/tmp/pr91_native_build_d3_20261020/source/overrides/module_em_c8_candidate.F`, SHA-256 `de21c8b0aad8c99ae1ed7de4e0e4fc77ebfc6050f998754c7ee6c3d27bfc90a2`.
- Shared store core: `src/common/cloud_bal_joint_transport.f90`, SHA-256 `c8ecedde5cc8f9adedf6cf082054596ca1c0d6a3565d152c73d730c00cd678f3`.
- Transformer output reproduced the emitted C8 source byte for byte. At the original review, `python3 -m unittest tests/test_pr91_source_store_contract.py` passed 3 synthetic tests. A follow-up run on 2026-10-20 passed the current 4 tests after the suite was expanded.

## Findings

No blocker found for the requested source-first pair-1 source-endpoint contract. The emitted source changes only two call sites in `prepare_source_first_rates`: both pair-1 stores pass `strict_mass_ratio=.TRUE.` and `volume_number_bounds=number_bounds(cell,:,p)`. Pair 2 retains its inactive-mass-limit path. The helper initializes pair-1 bounds from the same dry density and cloud PSD minimum/maximum constants used by the existing candidate path.

The first call checks the continuous pair through `joint_moment_store` before any storage adjustment: strict mass-ratio validity is checked at core stage 2 and the volume-number contract at stage 3. Normal-Q-directed storage adjustment is only attempted after those continuous gates and after R32 conversion/volume validity fails; rounded N is retained by the core routine. This is storage repair for an already valid pair. It adds no packet floor, PSD retuning, tolerance expansion, or new source prior.

The second pair-1 call is in the existing guarded representation fallback, after the first store has returned valid and the R32 endpoint safety/zero-underflow condition is tested. It now carries the same strict mass and volume options as the first call. The final consumer connection is present: the validated source endpoint seeds `donor_q/donor_n`; pair-1 `donor_values` returns that prepared donor on RK3, and `air_tendency` consumes it. The ordinary full-candidate path still validates/stores all pairs before the existing host commit block.

The C8 diff is limited to these two call sites. Pair-2, graupel-specific logic, failure/rollback handling, existing source-representation ledger, and commit ordering are unchanged in the emitted diff.

## Scope caveat

After the endpoint store, `source_sum64` adds the later non-air tendencies and becomes the virtual `donor_q/donor_n` used by the RK3 `air_tendency` consumer. For interior cells in `prepare_source_first_rates`, this post-endpoint virtual donor is checked by `prepared_donor_is_safe` only; it does not receive `joint_moment_is_valid64` or the pair-1 volume-number bounds there. A separate unchanged boundary-donor-ring loop does call `joint_moment_is_valid64` for those boundary donors. The normal complete-candidate store later receives the volume contract through the existing pair-1 storage path. If the intended contract covers the interior post-later-source virtual transport donor itself, this remains an open gate; the reviewed two-call change guarantees the source endpoint's contract only.

This was source review plus synthetic Python tests, not a C8 full-host compile or model run. Those remain owned by the root build/run validation.
