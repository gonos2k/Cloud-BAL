# PR87 V25 Shinhong PBL diagnostic cost note

Scope: read-only source/artifact review for `/var/tmp/pr87_joint_OFF_40s_v25diag_20261016`. This run is INCOMPLETE (receipt return code 1, final completed step 1). It is not a completed 40 s result.

## Observed artifact scale

Receipt-bound source: `module_bl_shinhong.F` SHA256 `adf3b78302832179839759fb2115fb65a3afd4233074b7e80a56a44239950c2a`.
Receipt: `docs/evidence/pr87_two_step_v25diag_20261016/runtime/OFF/receipt.json` SHA256 `b41b0a0b777ada6ae0e38dae9c6e743c43fe8834582bc1ff67cf44ac7b389c80`; wall time 333.586 s; completed step 1; status INCOMPLETE.

The packet ledger has SHA256 `9f1845655b7ade1d32c6361a53ad1b8e07d41847d03d77ed1f2fce20951fc514`, 830,505,357 uncompressed bytes, 201,012,270 gzip bytes, and 2,977,039 rows. Pair 1 contributes 1,633,101 rows; pair 2 contributes 1,343,938. A streaming decompression and local endpoint-classification pass took about 14.2 s on this host. This does not measure model-side write time.

The raw row stream has no model-step, RK, or invocation identifier. Do not attribute these counts to the first model call/step; they cover the output produced before this incomplete run stopped. Approximate linear planning only: at the observed row rate, 60 simulated seconds would be about 2.5 GB raw / 0.60 GB gzip; 600 seconds about 24.9 GB raw / 6.0 GB gzip. Counts and storage will not necessarily scale linearly as the state evolves.

## Source emission behavior

`shinhong` loops over `jts:jte` and calls `shinhong2d` per j column. With `pr85_packet_enabled`, `shinhong2d` handles QC/QNC and QI/QNI, solves each column's two REAL64 witnesses, and examines only exact-zero base pairs with positive source rates. `pr85_packet_roundtrip` checks exact-source validity at RK fractions 1/3, 1/2, and 1, then tests the legacy REAL32 stored candidate. A rejected pair restores both `f3` values to their `qx` bases, then opens, appends one CNUM_PAIR row, and closes the ledger for that one cell. Thus 2,977,039 rows entail the same number of per-row open/write/close sequences. The 64-bit solves and state/gate checks are also per-column work and would remain if only the writer changed.

The emitted row has coordinates, pair, DEL, exact Q/N rates, legacy Q/N rates, and DEL-weighted omitted source rates. It does not contain RK stage, timestep, or a reason code. Offline classification of the rounded ledger operands, bound to dt=20 and the source predicate, found every logged exact-source endpoint valid; first stored failure counts were:

| Pair | RK fraction 1/3 nonpositive | RK fraction 1/3 below lower | RK fraction 1/3 above upper | RK fraction 1/2 first failure |
|---|---:|---:|---:|---:|
| QC/QNC | 1,633,034 | 65 | 0 | 2 below lower |
| QI/QNI | 1,343,154 | 421 | 331 | 23 below, 9 above |

This is a replay classification from formatted operands, not a native emitted reason field or per-step count. Most RK1 nonpositive cases have a rounded Q source of zero. The residual columns are pressure-weighted (`DEL` times source rate), not kg or a physical mass budget.

## Existing reader reliance and low-volume option

No dedicated CNUM_PAIR budget parser was found. The runtime runner names the raw ledger in its trace-output collection list, and the policy JSON documents its row semantics; the PBL test checks source-level gate and write behavior. Preserve current full-row mode as the default and retain its filename/schema for existing evidence.

For short diagnostics, add an explicit opt-in summary-only policy that runs the identical solve, predicate order, `f3` reset, and gate, but replaces per-row I/O with in-memory accumulators. Emit one small summary per outer `shinhong` invocation (after its j loop), grouped by pair and first stored-failure stage/reason: count; signed/L1/max of DEL-weighted Q and N suppressed rates; and one selected full vertical tridiagonal column (matrix plus both RHS vectors) for a representative or worst failure per pair/reason. Include run/call identity and dt; use model-step/RK identifiers from the caller if available, otherwise label a local invocation ordinal and its mapping limit. Add a clearly named non-physical unit statement. Use a separate summary filename/schema and update receipt collection to capture it; do not silently change the legacy raw ledger format. Because reason counts do not exist today, add optional reason/stage outputs at the existing helper failure points without changing tests or inequalities; do not recompute the predicate in a second logger.

This mode avoids multi-gigabyte row files and millions of open/close operations. It does not remove the REAL64 column solves or guarantee a particular runtime; measure one 40 s run before extending to 600 s. Do not infer diagnostic performance from the whole-run wall time alone.
