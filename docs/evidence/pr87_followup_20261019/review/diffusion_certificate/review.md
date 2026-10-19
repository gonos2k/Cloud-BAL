# PR87 diffusion mixture certificate review

Reviewed 2026-10-19 against the frozen candidate below.

## Bound inputs

- `tools/pr87_graupel_cone_mixture.py` SHA-256: `66a8742c1f638fc3cea29fa73c7c8e3aeeeae2ce2a719a4ebd3ab0f022195b3d`
- `tests/test_pr87_graupel_cone_mixture.py` SHA-256: `105bae2f9abd12deda0c42e4963a844dd22cd33b6d1701d4c2a199290092816b`
- V48 `module_em_pr85.F` SHA-256: `45e74e6b4709b753dc501d965ac19cb4b9a021f4d8817cb195d4ced28640b8c5`
- V48 `solve_em.F` SHA-256: `9819ecab5e329cde214995bd192b1d6fee847809d8629498a3e5fe1c5b1de76f`

## Review and validation

The point replay matches the frozen `horizontal_diffusion64` stencil and its REAL128 operation order. Face ordering is E, W, N, S; the mixture subtracts the sum of positive face weights from the center and adds each weight to the corresponding neighbor. The production geometry references map to the diffusion caller: `grid%muts` and `grid%xkhh` flow through `rk_scalar_tend` as `mut` and `xkmhd`, with the same metric fields.

For a nonzero total Q/B source, the fallback requires exact REAL64 bit identity with the replayed QG/BG diffusion increments before building the mixture. A zero total source uses the air-only map under the documented source-total contract; this does not assert which physical process produced or canceled individual terms. The tests also exercise exact comparison against the frozen full helper, strict positive-weight donor validation, and transactional rollback.

Validation command: `pytest -q tests/test_pr87_graupel_cone_mixture.py` — **6 passed**. The two compiled transaction cases used `tests/intel_toolchain.sh` at pinned Intel O0 and O2 profiles in fresh `/var/tmp` scratch directories.

## Limits

The face-mixture expression is algebraically equivalent to the operator stencil, but its multiplication and summation association differs from the source replay. Exact replay validates the source increment; it does not make the reconstructed weighted candidate bit-identical to the canonical REAL64 RHS. This review validates the certificate and focused fixtures, not a native runtime cause, full-model conservation, or long-run scientific outcome.
