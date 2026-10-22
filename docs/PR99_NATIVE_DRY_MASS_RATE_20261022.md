# PR99 — observed native dry-column mass rate

The first captured acoustic MU update can be expressed in physical dry mass
without treating raw MUDF as an acceleration or an energy norm. At fixed
geometry the hybrid column measure gives

\[
\dot M_d=\frac{A}{g}\left[\sum_k(-C1H_k DNW_k)\right]
          \frac{MU^+-MU^-}{\Delta t}.
\]

C2H and the fixed base mass cancel in this difference. The calculation uses
the observed REAL32 endpoints promoted before subtraction, the captured
`dts=6.666666507720947 s`, the initial native map area, and pinned Intel
gravity `9.810000419616699 m/s²`. The hybrid sensitivity is
`0.9999999997256122`; it is computed rather than assumed to be one.

The 16 fixed QC-support columns are native i=134–137, j=16–19. All 57
snapshots per arm are bound to the closed original C1 20-second diagnostic
receipt, its unchanged input and executable, and its capture manifest.

| Arm | Signed sum (kg/s) | Column L1 (kg/s) | Column L2 (kg/s) |
| --- | ---: | ---: | ---: |
| OFF | 20,817,522 | 28,342,333 | 7,954,768 |
| HYDRO | 39,812,463 | 48,224,388 | 17,899,337 |
| COUPLED | 40,099,144 | 1,181,717,423 | 383,305,796 |

The similar HYDRO/COUPLED signed sums hide much larger column redistribution
in COUPLED. These support sums include exchange through the footprint edges;
they do not establish global dry-mass creation or loss. This is a conversion
of an observed update, not an independently closed horizontal/vertical flux
budget. It does not quantify momentum acceleration, observation skill, or
water/energy closure.

The [bound results](evidence/pr99_native_mass_20261022/observed_column_rate.json)
include per-arm maxima, their native locations and input/capture identities.
The [independent review](evidence/pr99_native_mass_20261022/independent_review.txt)
found no concrete algebra, coordinate or provenance blocker. Six focused
tests cover affine hybrid inventory differences, promotion before subtraction
and invalid geometry; file-join validation is exercised by the actual bound
analysis, not by a synthetic full-pipeline test. Scientific approval remains
`FAIL_OPEN`; observation skill remains `NOT_EVALUATED`.
