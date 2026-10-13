# PR84 same-13 native moment initializer

PR84 adds an opt-in `pr84_same13_native_moment_policy_v2` mode to
`tools/initialize_native_moments.py`. Invoke it through the existing
`--same13-policy` option. The v1 PR83 policy remains the default when explicitly
selected and keeps its fixed source cap and interior-only domain.

The v2 prior applies to the exact paired 13 UTC sources named in its policy
(`OFF` and `COUPLED`), at the declared 39 × 282 × 234 shape. It initializes
missing moments on all native horizontal columns, including the perimeter, and
all mass levels. It does not copy 12 UTC number fields. It preserves source Q,
temperature, vapor, geopotential, winds, CCN, and every other nonmoment field;
existing valid moment values are retained. Boundary and donor-period forcing
remain governed by the separate same13 boundary contract.

For QICE, v2 pins the retained consumer's REAL32 `PIDNI` value and bits and its
source `lambda_min`. It computes the exact source-parameter minimum public
QNICE in REAL64, stores the least REAL32 value at or above that bound, and
forms the REAL32 ceiling of the exact REAL64 internal-number floor. It advances
QNICE by the minimum number of REAL32 steps needed to satisfy both bounds:
the stored QNICE is at least the public floor and its REAL32 product with dry
density reaches the internal floor. The per-cell entry guard is
`max(1e6, REAL32(QNICE_floor * dry_density))`. This keeps the original
homogeneous-freezing number ceiling at low ice mass and permits only the
source-supported entry number needed for high ice mass. High-mass cells use
the exact minimum QNICE that satisfies the source PSD bound; low-mass cells
continue to use the existing midpoint prior under the 1e6 cap. No QICE mass,
temperature, PSD constant, snow, graupel, or other species value is changed to
resolve the cap.

The frozen policy binds the paired OFF and COUPLED input hashes, fresh KDM6
source, archive/member, executable, build receipt, actual `kdm6init` parameter
output and separate parameter dump, Intel profile, and WRF dry-density source.
The frozen pre-run policy marks the new consumer's runtime readback `NOT_RUN`;
completed model runs and readbacks are recorded separately in
[PR84_INTEGRATION_PROGRESS_20261013.md](PR84_INTEGRATION_PROGRESS_20261013.md).
The prior baseline readback is not presented as evidence for this new consumer. The initializer
cross-checks PIDNI, lambda minimum, shape exponent, and shape parameter against
both the receipt's source values and accessor output. It fails closed on any
mismatch and writes a new copy and receipt atomically. The receipt reports the
v2 schema explicitly. Both approved sources were initialized and passed
independent full-horizontal readback after the build review. The final producer
replayed both files byte-for-byte after the policy-hash guard was added. The
native first-step outcome remains rejected; initial-state validity is separate
from validity after PBL, advection, and RK.

The source-to-WPS trace in
[PR84_ICE_SPECIES_SOURCE_20261013.md](PR84_ICE_SPECIES_SOURCE_20261013.md)
supports keeping cloud ice separate from snow and graupel. It establishes a
mass-category mapping, not a measured crystal-size distribution. The cap
policy is a source-compatible initialization choice and does not claim an
observation-backed QNICE prior, a successful first KDM6 call, science
acceptance, or operational authority.

Focused unit contract:

```sh
python3 -m unittest tests.test_pr84_native_moment_policy tests.test_initialize_native_moments -v
```

No real source copy, model run, or compiler invocation is performed by these
tests. The v2 policy is source-bound in
[PR84_NATIVE_MOMENT_POLICY_20261013.json](PR84_NATIVE_MOMENT_POLICY_20261013.json).
The two authorized research runs preserved QNCLOUD, QNICE, QNRAIN, and QIB
through WRF initialization, then failed at NC number conversion before
completing KDM6. Their outcomes and artifact hashes are in the integration
report; the prior is not science or operational approval.
