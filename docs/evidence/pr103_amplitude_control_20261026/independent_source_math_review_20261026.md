# PR103 amplitude-control source and math review

**Decision: GO for one candidate-input construction.** This review does not
approve the resulting candidate, native-consumer result, forecast, physics, or
observation skill. No candidate input, forecast, or compiler run was made.

## Reviewed snapshot

- Builder: `tools/pr103_amplitude_control.py`, SHA-256
  `8a5cc8ab8bc34b61b2821d003e550bddbbce39de2b9f21a934eefe47941d004e`
- Policy: `docs/evidence/pr103_amplitude_control_20261026/policy.json`, SHA-256
  `32b916bb6789eeb83ba83798e639f48da73c6001444660d8113ed3c09d947696`
- Focused tests: `tests/test_pr103_amplitude_control.py`, SHA-256
  `3816f40f5da7f161e187f91d4384b0f88f517f044a16ee7762c54b6056baa920`

The source review confirmed one global scale from stored REAL32 P−H and N−H
over the inherited joint U/V free-face support; unchanged fixed/exterior faces;
byte-level PR99 continuous-P reconstruction; separate scaled continuous
reference and stored residuals with the actual stored-to-continuous error
checked against its bound; reused PR102 geometry for R(P), R(N), and R(A);
the inherited strict Δ gate; actual REAL32 readback norm validation; the
closed 32-step/640-second N receipt/preflight chain; source rechecks; and
cleanup of partial candidate and receipt outputs on failures.

## Checks

- `pytest -q tests/test_pr103_amplitude_control.py`: **9 passed**.
- `git diff --check` on the reviewed files: **passed**.
- Independent arithmetic: 3,000 deterministic mixed-exponent REAL32 cases
  compared with 100-digit Decimal calculations; zero ideal-formula or
  readback-bound misses (largest exact readback error was 0.9631 of its bound).
- Exact Fraction cases at signed scale 2, cancellation scale 1/2, sparse scale
  4, and large-background scale 1/4: **passed**.

The scale, PR99 equality, roughness, and norm checks are source/math gates. The
proposal remains pending native-consumer and source-capture validation;
physical approval remains `FAIL_OPEN` and observation skill remains
`NOT_EVALUATED`.
