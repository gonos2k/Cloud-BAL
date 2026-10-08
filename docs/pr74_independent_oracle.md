# PR74 independent analysis solver oracles

`tests/test_pr74_independent_oracle.py` checks the bounded linear estimator against references that do not construct or solve the production KKT system.

The scalar suite covers 396 combinations of signed targets and signed box endpoints. With unit prior and observation variances and `H = 1`, the objective has the closed-form minimizer `x* = y/2`; a box constrained solution is `clamp(x*, lower, upper)`. The specific regression with `y = -0.7` and bounds `[0.3, 1.3]` must select `0.3`.

For the six-state fixture, the reference uses the covariance update

```text
delta0 = B Hᵀ (H B Hᵀ + R)⁻¹ (y - H x0)
P      = B - B Hᵀ (H B Hᵀ + R)⁻¹ H B
delta  = delta0 + P Cᵀ (C P Cᵀ)⁻¹ (d - C delta0)
```

This independently checks the equality-constrained posterior mean. A second check changes only the units of `u` and `v` by 1000 and applies the corresponding covariance, observation, state, process, bound, and constraint transformations. The transformed optimum must equal the original optimum expressed in the new units.

These are manufactured algorithm checks. They do not validate Cloud-BAL runtime behavior, physical suitability of a declared objective, or scientific acceptance.
