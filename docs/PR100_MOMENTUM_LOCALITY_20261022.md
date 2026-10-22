# PR100: retained native momentum response locations

This analysis reuses the **closed PR99 projected U/V 20-second capture**
and the original **C1 HYDRO/COUPLED diagnostic captures**. It does not use
the separate C2 cohort or change the wind proposal, model, or physics.

The fixed 613-cell QC support maps to 769 U faces and 767 V faces. Captured
R32 operands are promoted before subtracting each operator's before/after
arrays. Each field remains in its own native source units. Initial wind
increments and their unweighted computational-grid second differences are
reported at the same native face indices.

## Where the retained differences occur

P denotes the native U/V projection and H denotes HYDRO. Fractions below
are sums of squared **P−H source-array differences** within the unchanged
support. They are not energy fractions.

| Captured field | Fraction in upper active levels k=37–39 | Largest P−H face (i,j,k) |
|---|---:|---|
| U advection call increment | 8.58% | (137,16,27) |
| V advection call increment | 13.60% | (136,17,27) |
| U horizontal diffusion call increment | 81.88% | (136,16,39) |
| V horizontal diffusion call increment | 81.98% | (135,17,39) |
| Assembled RU | 67.12% | (136,16,39) |
| Assembled RV | 55.49% | (135,17,39) |

At those upper-level diffusion maxima, initial P−H wind increments are
U=+7.846 and V=−7.224 m/s, respectively. These are different faces. Their
computational-grid curvature diagnostics are also nonzero. The retained
diffusion response is therefore concentrated near specific upper-level
wind structures; the advection difference peaks lower, around k=26–28.

This narrows the next source inspection to the upper-level wind transfer,
stencil, coupling, and diffusion coefficients at those faces. It does not
establish which of those operations caused the response. The initial
wind curvature diagnostic is **not** the actual native diffusion operator.
Native k is a level index, not a geometric height.

## Interpretation limits

The projection's observed mass-response improvement is preserved. No
smoothing, cap, weight, or new null-space correction is applied here.
HDIF tendency arrays and assembled RU/RV are not added across their
different source conventions. Captured RU/RV remain coupled RHS arrays,
not physical acceleration; subsequent boundary, acoustic, and wind
restoration states are still required for that conversion.

The [bounded evidence](evidence/pr100_momentum_locality_20261022/README.md)
includes the calculation and independent review. The reviewer verified
receipt/input identities, all 30 consumed capture hashes, face indexing,
and agreement with the existing PR99 response norms. This supports the
descriptive locations above. Physical approval remains **FAIL_OPEN** and
observation skill remains **NOT_EVALUATED**.
