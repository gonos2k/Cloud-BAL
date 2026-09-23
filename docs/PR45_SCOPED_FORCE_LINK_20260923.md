# Scoped force links after PR44

Base: merged PR #44, `7d356f8b6eb7e1c686720b39a4578c5c3ddb9991`.
These are read-only, same-case diagnostics. No retained HT, T/q, wind, balance
solver, production input, or native state is changed. The earlier controlled
replay varied `CLOUD_SWITCH` only in copied run roots.

## PR44 validator follow-up

`compare()` now requires finite supported `before`, `after`, direct change,
retained HT, and nonnegative finite arithmetic bounds with matching shapes.
Unsupported NaNs remain valid. `paired_inputs()` rejects directory and broken
symlinks rather than silently omitting their contents; regular file links are
still compared by content. The focused tests reproduce the reported P2 cases.
Rereading the retained actual13 evidence with the hardened validators left all
scientific values and support counts unchanged; only validator source hashes
changed in the new receipts.

## Conditional ground profile versus retained HT

On the frozen PR43/44 support define `S = Phi_a^G - g0*HT`, direct
`D = Phi_f^G - Phi_a^G`, and `F = Phi_f^G - g0*HT`. The new diagnostic uses
PR43's directly accumulated `D`, checks `F-S=D` within the original uncancelled
arithmetic bound, and applies PR42's same P1 triangle gradient and equal-area
east/north metric to all three scalar fields. It neither chooses a new datum
nor modifies the original height field.

All 98 supported triangles, with 1,959 triangle-pressure instances, lie in
PR42's force support. The acceleration-magnitude RMS values over **that exact
intersection** are:

| Conditional component | RMS, m/s² | Maximum, m/s² |
|---|---:|---:|
| `-grad S` | 0.0129856 | 0.0664491 |
| `-grad D` | 0.000923422 | 0.00403273 |
| `-grad F` | 0.0129179 | 0.0664172 |

These are magnitudes of separate vector fields; their RMS values do not add.
The largest nodewise `F-S-D` residual is `9.91e-11 m²/s²` versus a maximum
node arithmetic bound of `5.88e-8 m²/s²`. The largest force-vector linearity
residual is `2.03e-14 m/s²` versus a propagated bound of `5.38e-11 m/s²`.
The maxima occur at different triangles or pressure levels. The original
PR42 maximum-force triangle 75,455 remains outside this ground selection.

`S` includes the conditional surface representation, datum and old producer
operator differences. Its force magnitude is **not** a measured model error
or permission to replace HT. `D` is the conditional matched-layer T/q change;
its ground reference differs from PR42's 5000 Pa zero gauge.

## Cloud ON/OFF at the PR42 maximum triangle

The second diagnostic holds the retained final LT1 temperature fixed and
uses the humidity producer's ON minus OFF LQ3 specific humidity:

```text
delta_Tv_cloud = (1/0.622 - 1) * T_final * (q_ON - q_OFF)
delta_Phi_cloud(p) - delta_Phi_cloud(5000 Pa)
    = Rd * integral[p to 5000 Pa] delta_Tv_cloud d(ln p)
delta_a_cloud = -grad_p(delta_Phi_cloud)
```

The same PR41 pressure levels, connected support, PR42 triangle and centroid
metric are used. At triangle 75,455 and 100000 Pa the conditional relative
east/north acceleration is `( +0.01452390673, -0.01321726560 ) m/s²`, with
magnitude `0.0196377 m/s²`. The triangle has 20 supported levels from 100000
to 5000 Pa; the zero at 5000 Pa is the declared gauge. This is the net late
cloud-block **plus subsequent QC** effect at fixed final T. It is not an
observed acceleration error, wind increment, or proof that the moisture
analysis is meteorologically right.

At node `(55,162)`, integrating the ON-OFF profile over 19 supported regular
layers from 100000 to 5000 Pa gives `+9.802161313 kg/m²` of conditional
vapor-column change. The ground-to-100000 Pa partial layer, condensate,
transport, precipitation, and energy terms are absent. This number is not a
complete moisture budget or predicted rainfall.

The two force diagnostics answer different questions and cover different
domains: ground `S/D/F` is supported on 98 triangles; cloud ON/OFF is evaluated
at the maximum triangle, where the ground reference is unsupported. The new
calculations do not create a joint balance candidate or authorize BALCON ON,
native initialization, or forecast use.

Reproduction and hashes are in the compact
[ground-force](evidence/pr45_ground_ht_force.json) and
[cloud-force](evidence/pr45_cloud_force.json) receipts. The hardened PR44
[ground](evidence/pr45_ground_ht.json),
[cloud O0](evidence/pr45_cloud_O0.json), and
[cloud O2](evidence/pr45_cloud_O2.json) receipts show the unchanged numerical
results with current validator source hashes. Large source arrays remain in
scratch; the receipts bind them by SHA-256.
