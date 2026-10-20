# PR91 host-store trace team review

Review date: 2026-10-20. This was a read-only review of `tools/pr91_host_store_trace.py`, `tests/test_pr91_host_store_trace.py`, the generated D3 host writer, and [the diagnostic contract](../../PR91_HOST_STORE_CONTRACT_20261020.md). No source or runtime artifact was changed for this review.

## Reviewed identities

| Item | SHA-256 |
|---|---|
| Transform tool | `3f694f9ecfd19d8ce93c59feab64d12382ba789d80755851eb477735a26850e8` |
| Transform tests | `79d92b5bfc612bc97112dd38669452ad443a923c7ecd1ea7c9fb2da130053e85` |
| Hash-pinned source host | `090b9329c817f52f0fba45d6d97f93a6bdb35adc5f46cfed0ae198b15401819b` |
| Hash-pinned shared core | `c8ecedde5cc8f9adedf6cf082054596ca1c0d6a3565d152c73d730c00cd678f3` |
| Generated D3 `module_em.F` | `dc21f48b29784f7ab6bbb6975ef541d184b31effa796b0e5aab51b16e80d406d` |
| Generated shared-core overlay included in the host transform | `9cfc20a3724b9a71b0be912d7f6746cd3ae5f17128dd743539a34ddadfd862a6` |
| D3 build receipt | `e58f116cc4157623298cacae1744eecfa466ccb023f5519c139472f39f37450c` |
| D3 executable (build receipt) | `89812febe43ac6afb7388e5aed7395614527c46ffee8c9eb3dcbad1ba807f97a` |

The generated files in `/var/tmp/pr91_host_store_trace_transform_20261020_i/` match the current pinned transform byte-for-byte when regenerated in memory from the pinned source files. Earlier transform artifacts are superseded and were not used for the semantic findings below.

## Review findings

- **Diagnostic scope and sparse indices:** the six selected coordinates match the six prior C7 `FULL` failure locations: `(130,182,2)`, `(194,80,22)`, `(132,201,19)`, `(196,211,16)`, `(168,225,20)`, and `(231,240,20)`. Their flattened-cell lookup uses the same `j,k,i` loop order and bounds as host array construction. This is sparse diagnostic capture; it does not select or modify a physical candidate by cell.
- **Attempt scale and failure stage:** `diagnostic_scale` receives the `scale` argument from the actual `form_candidate` call where `joint_moment_store` fails. This constrained-storage call uses the full scale `1.0`; it does not infer scale from the subsequent replay. `diagnostic_stage`, candidate/stored values, and adjustment are copied at that store call before the caller writes failure sentinels.
- **Numeric and HEX record layout:** the actual generated writer's record has 19 ES values, 10 64-bit HEX values, 8 32-bit HEX values, and 2 integer tail values, matching the supplied operands and bit-transfer fields. The current mixture writer uses scalar `SIZE=7` for `TRANSFER` array captures. The older `_f` artifact's rank-one `[7]` form is stale and is not the D3 source.
- **Physics-path effects:** with the declared, correctly sized diagnostic arrays and a valid run identity/output path, added core operations initialize/copy diagnostic outputs and expose the existing store stage; they do not change candidate formulas, bounds/options, FP policy, commit, or rollback. The host writes actual failed-store information before continuing into the existing fallback logic.
- **Diagnostic failure gate:** the contract correctly limits the no-change claim. `PR91_RUN_ID` and a writable run root are required. Missing identity or trace-file open failure takes a fail-closed fatal path; the contract explicitly states that these diagnostic-error paths are not claimed to match the uninstrumented host. This is an intentional diagnostic gate, not a claim that every error path is unchanged.

## Remaining constraints and open work

The trace selects only six predeclared locations and records rows only for failed actual store calls (`failure_stage > 0`). Runtime preflight must verify `PR91_RUN_ID` and a writable run root before launch; the trace artifact must be tied to that run ID. The D3 partial-host build identity does not establish a native run result.

The physical cause of the T10 rejection and identity of the actual native prefix remain **pending**. Synthetic writer/replay behavior, build success, and this source review do not identify a failing physical predicate or prove that a later runtime reproduces the preserved prefix. The OFF diagnostic execution and subsequent paired validation remain open in the contract.
