# PR98: native response and same-call water accounting

The frozen PR96-C1 OFF, HYDRO and COUPLED 600-second runs remain the reference.
This change adds source-bound diagnostic captures and reducers. It changes no
forecast equation, balance weight, moment prior, precision policy or tolerance.

## Additional wind correction

The initial HYDRO and COUPLED `wrfinput` files differ only in U and V among all
208 stored variables. A diagnostic overlay captures the actual first native
momentum assembly and dry-mass update. All three 20-second diagnostic runs
complete, with the checked first-step trace, T1 microphysics fields and T0
history fields matching the frozen C1 results.

HYDRO disables the continuity and force priors together. This contrast
measures their combined wind treatment; it does not identify either prior's
individual effect. The geostrophic-objective discussion below concerns one
part of that treatment.

On the fixed support, COUPLED has larger assembled RU, RV and RW norms than
HYDRO. The selected operator captures show substantial changes in advection
and horizontal diffusion, while the C−H pressure-gradient contribution is
nearly zero. The pressure-level geostrophic objective does not include these
native operators.

| Captured source-array L2 | HYDRO | COUPLED |
|---|---:|---:|
| Assembled RU, 769 U faces | 24,361.966 | 41,212.461 |
| Assembled RV, 767 V faces | 23,908.715 | 34,050.805 |
| Returned MUDF, 16 columns | 6.893418 | 147.642661 |

Summing the captured pressure-gradient and Coriolis arrays before taking
norms gives a smaller selected partial RHS in COUPLED: RU L2 is about 24,025
versus HYDRO's 24,263, and RV is 23,618 versus 23,848. This reduction in two
selected source terms does not establish a reduction in the complete captured
assembly. It is not an exhaustive attribution or momentum closure.

Review corrected the distinction between the cropped history origin
`(i=2,j=2,k=1)` and the dynamics tile origin, and promotes captured REAL32
operands before diagnostic arithmetic. Independent composition-to-native
index calculations and targeted regressions verify the corrected results.

**The additional correction is not approved as a reduction of the measured
native initial tendencies.** Preserve C1 as the reproducible research baseline;
use the reviewed operator attribution before proposing a change to the wind
objective.
This conclusion concerns the captured first call and fixed support. Raw coupled
RHS norms are not acceleration or energy, OFF is not truth, and independent
observation skill remains `NOT_EVALUATED`.

See [the native analysis](PR98_NATIVE_EFFECT_20261022.md),
[capture provenance](PR98_NATIVE_CAPTURE_20261022.md), and the
[same-level support map](evidence/pr98_native_maps_20261022/same_level_response.png).
The map uses saved states; it is not an operator or flux closure.

## Same-call water accounting

The independently recorded cutoff assignments explain an additional
−43,406.915 kg in OFF's T1 call. Subtracting the liquid storage term and this
cutoff term changes the unexplained signed residual from −66,056.548 to
−22,649.633 kg. At the previously largest unexplained column `(184,147)`,
the remaining value falls from −61.123674 to −0.556383 kg. The positive
column `(208,79)` supplies a separate process/sign check.

These are measured state removals at existing numerical cutoffs, not fitted
residual corrections or physical phase transfers. A separate observer records
accepted rain and ice sedimentation packets and their actual donor/receiver
store changes. This contribution includes representation and arithmetic
effects; it is not assigned from the endpoint residual or classified as pure
REAL32 rounding.

| Arm | Accepted face/store term, kg | Remaining signed residual, kg |
|---|---:|---:|
| OFF | +8.620113 | −22,658.253498 |
| HYDRO | +9.683884 | −22,655.157443 |
| COUPLED | +16.461963 | −22,683.387674 |

Subtracting this positive term makes the signed residual slightly more
negative. Its column L1 is about 12,047–12,054 kg, distinct from its signed
sum. All three observer replays reproduce the 17 returned fields and XLAND
byte-for-byte. See the [T1 analysis](PR98_T1_RESIDUAL_20261022.md) for independent
terms, local checks, provenance and remaining processes. Host hybrid water,
energy and mass–wind closure remain open.

## Repeated consumption beyond 600 seconds

The frozen C1 executable is used for three 640-second requests. Their final
result is tracked separately in the
[boundary report](PR98_C1_BOUNDARY_20261022.md). A running request is not a
completed regression. The earlier C4 grouped failure and its subsequent
per-cell callbacks do not establish what will happen in C1.

## Approval boundaries

| Item | Meaning |
|---|---|
| Original C1 three-arm 600-second execution | Complete baseline retained; aggregate review remains required |
| Diagnostic captures and replay identity | Evidence for the explicitly compared fields and calls |
| Added wind correction reduces native initial response | Not demonstrated by the captured indicators |
| Same-call T1 accounting | Additional independent terms explained; residual still open |
| Original endpoint / active-ice / generic audits | Source endpoint PASS; active-ice policy PASS; generic FAIL retained |
| Full water/energy/mass–wind closure | `OPEN` |
| Independent observation skill | `NOT_EVALUATED` |

Graph freshness and diagnostic test counts do not establish runtime or
scientific approval. The new captures are partial-host research overlays,
not a clean rebuild of the full WRF model and its dependencies.
