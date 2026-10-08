# PR75 KKT stationarity certificate (2026-10-08)

The normalized KKT residual now uses an operand scale built before cancellation.
For each normalized control coordinate, it sums the absolute terms contributing
to the background gradient, the expanded observation gradient
`Hscaledᵀ R⁻¹ residual_scaled`, and the equality-multiplier term. The residual
itself remains the absolute Lagrangian-gradient imbalance divided by the largest
coordinate operand scale (with the smallest positive float as the zero-scale
floor). The stopping tolerance is unchanged.

This fixes the unconstrained scalar case `B=1`, `R=1`, `H=2`, background `0`,
observation `1`: the minimizer is `x=0.4`; its two gradient contributions are
`+0.4` and `-0.4`. The former scale was formed from the cancelled gradient and
therefore rejected a correct solve when floating point left a residual near
`1.11e-16`. The operand scale represents the backward error of that cancellation.

Stationarity operand-scale overflow raises a controlled `NUMERICAL_FAILURE`.
Primal equality and bound residuals, dual sign, complementarity, rank checks,
and the rejection of an intentionally perturbed solution remain enforced.
No final clipping or tolerance increase was introduced.

## Validation

- `python3 -m unittest tests.test_pr73_joint_analysis -v`: 20 tests pass,
  including the unconstrained scalar regression, active lower/upper/fixed bounds,
  equality and bound interactions, and rejection of a perturbed solve.
- This Python-only change did not run the pinned Intel endpoint integration;
  that validation is recorded by the parent task owner.
- Graphify was used to navigate the existing Cloud-BAL graph. Persistent graph
  updates and the separately dated KG snapshot are handled by the parent task.

## Scope

This certifies only the declared small linear `H/B/R` optimization problem and
its constraints. It adds no physical authority and does not change the existing
native `REJECTED` / physics `FAIL_OPEN` status.
