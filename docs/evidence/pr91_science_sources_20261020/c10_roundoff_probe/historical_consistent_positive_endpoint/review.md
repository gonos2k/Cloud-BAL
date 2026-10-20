# C10 diffusion cancellation probe — 2026-10-20

## Result

The roundoff concern remains possible with a consistent ordinary producer rounded-addition relationship. In this manufactured case `t_after32` is formed as `REAL32(REAL64(t_before32)+Dold64)` and rounds to `t_before32`. Exact rational arithmetic gives a zero total, while pinned Intel O0 and O2 both leave `qs64=-2^-54`. With the selected unit carrier and `dt=20`, the prepared endpoint remains 1 and the virtual donor is `1-5*2^-52` (`0x1.ffffffffffff6p-1`), so the donor stays positive.

This remains a binary64 counterexample only. It uses no actual C10/C11 native failure bits and does not establish that this mechanism caused the C10 failure or is reached by C11.

## Arithmetic and exact reference

Inputs: `t_before32=1`, `Dold64=2^-54`, `t_after32=REAL32(REAL64(t_before32)+Dold64)=1`, `coupled_before32=1`, `Dprepared64=0`, zero other non-diffusion residual, unit carrier, and `dt=20`.

The unrounded rational terms are:

- `laterResidual = t_after - coupled_before = 0`
- `deltaPrecision = (1 + 2^-54) - 1 = 2^-54`
- `Dprepared - Dold = -2^-54`
- exact total = `0`

At 1.0, the upward binary64 spacing is `2^-52`; `2^-54` is below half an ulp (`2^-53`), so the binary64 addition `1+2^-54` rounds to 1. The computed precision difference becomes zero. Sequentially adding the prepared-minus-old diffusion difference then leaves `-2^-54`. This residual is propagated by the specified donor calculation to a small decrement from the positive endpoint.

The Fortran fixture follows the C10 producer endpoint rounding, the later residual and precision-difference expressions from the hypothesis, and the C10 prepared-minus-old and donor arithmetic. The exact reference is independently calculated with Python `Fraction`. Both O0 and O2 output records are byte-identical and pass the signed-residual assertion.

The first probe, which independently set `t_after32=0` despite `t_before32=1`, is retained under `historical_independent_endpoints/`. That case demonstrated a negative donor from a zero endpoint but did not establish the producer relationship. The consistent case above is primary and replaces it for evidence claims.

## Conditional diagnostic/design response

If C11's captured operands reproduce this path, cache producer-stage `t_before32`, `t_after32`, and `coupled_before32` at the same RK1 footprint and retain the existing geometry identity. Form the new-state residual directly from those endpoint states and include each non-diffusion addition once, plus the prepared diffusion result once. Keep old diffusion for existing ordinary-source bookkeeping, but avoid subtracting it from a reconstructed rounded precision-correction scalar. Do not add an epsilon or widen precision. This is a follow-up hypothesis, not an implementation request or causal finding.

## Reproduction and pins

The primary fixture is compiled and executed only with the pinned Intel profile in `tests/intel_toolchain.sh`, using required O0 and O2 flag arrays in fresh `/var/tmp/pr91_c10_roundoff_probe_20261020/{o0,o2}` directories. See `roundoff_probe.f90`, `run_command.txt`, `ifx_o0_o2.log`, and `exact_rational_result.json`. No physics source, model code, or native instrumentation was changed.
