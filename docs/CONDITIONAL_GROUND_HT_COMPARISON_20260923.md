# Conditional ground profile versus retained HT

Base: PR #43, `5f51fbbcec8d7908ce4e91f9d59394927348a917`.
Status: `PASS_SCOPED / CONDITIONAL_STAGE_HT_COMPARISON`.

PR #43 computed two conditional geopotential profiles from a common ground
datum and the same 0–10 m thermodynamic prior. This follow-up compares both
profiles with the *unchanged* retained LT1 HT at exactly the supported node
and pressure levels. It does not construct a corrected height field.

For stage `a` and final analysis `f`, the reported quantities are

```
S = Phi_a^G - g0*HT_retained
F = Phi_f^G - g0*HT_retained
D = Phi_f^G - Phi_a^G, accumulated directly from matched T/q layers
F - S = D
```

The conversion `g0*HT` uses the same constant `g0=9.80665 m/s²` as the
conditional model. `S` includes differences in the old producer's operator,
height datum, and the conditional surface representation. Its size does not
measure an observed height error. `D` is a model difference, not a permission
to add it to retained HT: doing so leaves `-S` against the constructed final
profile. Both comparisons use the same mask; neither bridges a missing layer.

The retained PR43 ground arrays, PR41 paired-state stream and original LT1
file are checked by SHA-256 before the calculation. PR41 already checked that
its captured HT is float32-identical to retained LT1. This run also compared
all 1,463,110 stored HT values directly with the retained NetCDF product;
they match exactly after the documented axis and pressure reversal.

## Same-case result

The frozen PR43 selection supports 876 of 66,505 nodes and 17,182 node-level
values. The maximum-force triangle 75,455 remains outside this selection.
Values below are in m²/s², on the same supported node-level set.

| Quantity | Minimum | Maximum | RMS |
|---|---:|---:|---:|
| `S`, conditional stage minus retained HT | -828.663600 | +1032.271144 | 163.955209 |
| `F`, conditional final minus retained HT | -830.758850 | +1031.266757 | 165.472271 |
| `D`, final minus stage | -24.173217 | +51.117346 | 8.831936 |

Dividing the two RMS values by the declared constant `g0` gives 16.72 m for
`S` and 0.90 m for `D`. These height-equivalent numbers use the same comparison
convention; they are not observed height errors.

The largest absolute `S` is at `(i,j)=(149,85)`, 5000 Pa. There the
**colocated** `S`, `F`, and `D` are +1032.271144, +1031.266757, and
-1.004388 m²/s². Maxima from different locations are not added.

At 100000 Pa only 599 selected nodes are supported; all 876 are supported
at 85000 Pa and above. Per-pressure counts and ranges are in the
[JSON receipt](evidence/pr44_ground_ht.json).
Do not compare pressure-level extrema as though their spatial samples match.

The identity `F-S=D` passes with a rounding allowance based on the PR43
uncancelled arithmetic bound and the two retained-HT subtractions. This bound
is numerical only. The original PR43 pinned Intel O0/O2 ground test passed
55 assertions at each optimization in fresh scratch. The new Python comparison
has two synthetic tests for cancellation, unsupported NaNs and closure failure.
No new Fortran scientific kernel or producer was introduced.

Reproduction with the hash-bound PR43 output:

```bash
python3 tests/diagnose_qbal_ground_ht.py \
  --ground-dir /path/to/pr43/ground_final_v3 \
  --output-dir /new/scratch/ground_ht
python3 -m unittest discover -s tests -p test_qbal_ground_ht.py
```

This closes the supported-set `Phi_a^G - g0*HT` accounting. It does not
resolve the surface datum, lower thermodynamic profile beyond 10 m, 0–10 m
wind transport, maximum-force location, or an authorized joint balance state.
The retained FUA/FSF pair also lacks a bound writer/frame/coordinate receipt;
it is not silently mixed with LT1/LSX to extend support.
