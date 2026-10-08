# Degenerate equality/bound certificates — PR76

Base: PR75 main `fd7e1be37075a7ba80ee3a0be080111a5be03a26`.

## Reproduced failure

The declared strictly convex objective is

\[
J(x,z)=\tfrac12(x^2+z^2)+\tfrac12[(x+1)^2+(z-1)^2],
\quad x+z=0,\quad 0\le x,z\le1.
\]

The feasible set is the singleton `(0,0)`, with cost 1. PR75 computes that state but rejects the multiplier representation attached to its first chosen face. A legal witness exists: equality multiplier 1 and lower-bound multipliers `(2,0)`.

This is an existence question. A free coordinate in the face solve can reach a bound in the returned state, and equality rows removed on free coordinates can still provide stationarity components on active coordinates. A failed particular multiplier representation does not invalidate the primal optimum.

## Implementation

`tools/pr73_joint_analysis.py` retains the primal face enumeration and exact bound assignment. Certification now uses the returned state's actual active bounds. For normalized objective gradient `g`, independent equality rows `C`, and signed active normals `N`, it seeks

\[
g+C^T\lambda+N\mu=0,\qquad\mu\ge0.
\]

Fixed coordinates are removed from this sign-constrained problem and have unrestricted multipliers. Projecting onto the complement of the equality row span gives

\[
P N\mu=-P g.
\]

For the existing limit of eight variables, the helper enumerates independent supports of the projected bound normals. A nonnegative cone representation needs at most the coordinate dimension in exact arithmetic. It then recovers equality multipliers and reconstructs the full stationarity equation. The final diagnostic recomputes primal feasibility, stationarity, signs and complementarity from that witness.

The projected residual scale uses uncancelled objective operands, preventing another self-normalization failure. The existing `4096*epsilon` threshold is unchanged. No bound clipping, tolerance increase, removal of sign checks, or arbitrary tie-breaking is used. Normalized equality rows and multipliers are exposed for independent replay.

Gram solves can square conditioning. Near-dependent constraints or a failed numerical certificate remain `NUMERICAL_FAILURE`; this small reference is not a general LP solver or an operational atmospheric optimizer.

## Verification

- 24 focused original solver tests, including the reported singleton, reversed variable order, equality-aligned active bounds, fixed coordinates and wrong-certificate rejection.
- Independent Fraction witnesses: 162 manufactured optima (two singleton orderings and 160 mixed-face cases), with duplicate equalities, all 24 four-variable permutations cycled, powers-of-two unit changes and lower/upper/fixed faces. A feasible nonoptimal control fails the exact KKT/objective reference.
- Root validation: 68 Python test methods, retaining earlier scalar, covariance, mixed-unit, rank and rejection checks.
- Fresh pinned Intel O0/O2 estimator fixture endpoint/writer/reader compilations in scratch: component readback passes. The canonical diagnostic remains `UNBOUND/REJECTED`; the production pipeline is not executed.

The manufactured case counts are not an error-rate estimate for weather data. Native FP policy, moment acceptance, carrier conservation, water/energy closure and time-response evidence belong to separate gates.

Exact declarations, before/after results, source hashes and logs are retained in `docs/evidence/pr76_degenerate_reproduction_20261008.json`, `pr76_degenerate_kkt_oracle_20261008.json`, and `pr76_degenerate_endpoint_20261008/receipt.json`.

Overall physical initialization remains **FAIL/OPEN**. See `PR76_PHYSICAL_CLOSURE_CHECKLIST_20261008.md`.
