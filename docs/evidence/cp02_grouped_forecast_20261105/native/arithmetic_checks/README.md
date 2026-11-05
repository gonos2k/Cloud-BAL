# Grouped forecast REAL32 arithmetic check

This check isolates the four-term numerator from the prior `calc_p_rho_phi` source pin:

- Old: `(ph(k+1)-ph(k)+phb(k+1)-phb(k))`
- Grouped: `((ph(k+1)-ph(k))+(phb(k+1)-phb(k)))`

`inputs/phi_rows.json` records 15 paired calls each from `phi_p20183` and `phi_p17051`, with B1 and DM065 arms: 30 interarm pairs and 60 finite REAL32 input rows. The raw analysis fields are little-endian byte hex; `inputs/phi_terms.hex` reverses each byte string into the integer spelling consumed by Fortran `Z8` input before `TRANSFER` to REAL32. Both forms and their source hashes are retained.

Run `runner/run_checks.sh` from this worktree. It creates a unique fresh attempt below `runtime/arithmetic_check/`, sources the pinned `tests/intel_toolchain.sh`, compiles O0 and O2 strict-profile variants, captures stdout/stderr, compares both against the independent exact-Fraction validator, and writes logs, results, and a hash-bound receipt. Never substitute another compiler or run in the source tree.

## Result

The pinned Intel IFX 2026.0.0 O0 and O2 builds and executions passed. Both outputs match the independent binary32 references for all 60 rows. Grouped equals the exact rational result rounded once in all 60 rows; the old sequential expression differs from that result in all 60 rows. The results table includes the exact old/grouped references and the pairwise interarm deltas.

This is a REAL32 unit arithmetic result for captured inputs only. It does not prove WRF machine instruction order, runtime model behavior, forecast impact, physical mass conservation, or scientific acceptance. The native full-model owner must establish compiled-model ordering separately. No model or scorer source was modified.

Receipt: `receipts/arithmetic_validation.json`.
