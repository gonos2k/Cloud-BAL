# PR87 small positive ProgB graupel domain review

Read-only source review of the frozen KDM6 V42 source at
`/var/tmp/pr87_joint_cycle_sources_20261016_v42/module_mp_kdm6.F`.
SHA-256: `bdb1882afed860068cecbb6c7b958eef0938cadbd4225222ba7522e28ecc071a`.
No code, build, or model-run changes were made.

## State and units

The two ProgB prognostic moments are graupel mass mixing ratio `QG` and graupel
volume mixing ratio `BG`. In this source's budgets they are represented as
kg/kg-dry-air and m3/kg-dry-air, respectively; `QG/BG` is particle bulk density
in kg/m3. The paired sedimentation ledger converts them to area inventories
kg/m2 and m3/m2. `qcrmin=1e-9` kg/kg-dry-air and `pr85_brs_min=1e-15`
m3/kg-dry-air (`module_mp_kdm6.F:116-117`).

`ProgB_param` (`:6750-6904`) treats exact `(0,0)` as absent, rejects a
one-sided zero, marks a positive pair transient only if both `QG<=qcrmin` and
`BG<=1e-15`, then otherwise requires finite `100<=QG/BG<=900`. Its table
coefficients depend on the ratio, not the magnitude. For every positive
pair in this density interval, scaling QG and BG by the same positive factor
preserves the same defined density and coefficients. In the tiny-mass branch,
`slope_kdm6` already uses finite maximum-slope constants when `QG<=qcrmin`
(`:7007-7021`) instead of evaluating the `log(pidn0g/(QG*den))` reconstruction
used above that threshold (`:6951, :7014-20`). This is a finite, existing
small-mass branch, although its process kinetics are piecewise and are not
homogeneous in QG: several collision and number-rate paths turn on only for
`QG>qcrmin`, while deposition and melt mass terms can be driven by the
density-based PSD coefficients. State homogeneity should not be confused with
scale-invariant rates.

## Producers and consumers

- Entry copies host `qg` and `bg` into `qrs(:,:,3)` and `brs` without a graupel
  number conversion (`:1467-1472, :1517-1534`). Surface fall moves paired mass
  and volume through `pr85_kdm6_paired_sediment_column` (`:2713-2723`); the
  helper makes proposals and storage changes in REAL64, rounds candidate
  endpoints to REAL32, and validates each rounded pair's density
  (`tools/pr85_kdm6_ice_sedimentation.F90:106-110, :344-399`).
- Cold process admission combines Q, number, BG, temperature, and vapor deltas
  and validates rounded stored states before committing them atomically
  (`module_mp_kdm6.F:502-504, :5160-5191, :5462-5484, :5510-5587`). BG
  contributions are mass-rate divided by the corresponding particle density
  (`:482-500, :5021-5058`). Graupel melt has a separate Q/BG transaction;
  number conversion is only performed above qcrmin and BG loss uses the same
  density pair (`:3052-3115, :3136-3177`). Warm melt and evaporation use
  `QG>0` for bounded donor mass, while the graupel number update is gated by
  `QG>qcrmin` (`:4594-4604, :4746-4752`).
- Major graupel collection and number consumers are gated on active status and
  `QG>qcrmin` (`:4184-4192, :4239-4247, :4279-4297, :4420-4453`). These are
  existing process thresholds and can remain as-is if small positive states
  are admitted as active.
- The end-of-loop cleanup zeros QG and BG and sets status absent whenever
  `QG<=qcrmin` (`:6274-6295`). This is a distinct terminal cutoff: it means the
  current implementation can use a small positive state during the process
  transaction but intentionally does not preserve it as a call output.
- `kdm6_refresh_graupel_intercept` validates the positive intercept using
  REAL64 intermediates and finite/overflow checks (`:214-244`); the earlier
  in-loop assignment `n0go=n0g/g1pmg/rslopemu` has no equivalent local check
  (`:2910-2914, :3877-3880`). Under the active small-Q branch, its inputs are
  fixed finite constants. A tiny QG itself is not divided into this intercept.

## Minimum common small-positive policy

For intermediate KDM6 states, define one policy for each producer, consumer,
and process endpoint: exact `(QG,BG)=(0,0)` is absent; otherwise both moments
must be finite and strictly positive and their REAL64 ratio must lie in the
existing closed `[100,900] kg/m3` support. Do not make `qcrmin` or
`pr85_brs_min` an additional state-validity floor. Retain `qcrmin` where it
selects existing slope and interaction-rate branches, and retain the explicit
end-of-loop cleanup if the call contract still requires that cutoff. Apply the
same pair predicate in `ProgB_param`, process fraction/state validation, and
the PR85 paired graupel sedimentation helper; leaving its local low/low reject
would still reject valid small stored endpoints.

For the current domain (QG near `1e-9` down to the density-implied transition
near `1e-13`), ratio construction is safe: the division is REAL64 and the
accepted result is bounded 100-900 before conversion to REAL32. The
QG<=qcrmin slope fallback avoids a small-denominator lambda calculation.
Sedimentation uses REAL64 packets then validates REAL32 stored endpoints, and
melt checks finite/overflow before converting number and volume rates. The
remaining numerical boundary is storage resolution: for states approaching
REAL32 subnormals, adding a physically smaller process increment may round to
the same stored value or extinction; this is not a reason to add a physical
species floor. Preserve the existing conservation/residual checks and test
candidate endpoints after REAL32 rounding. The in-loop evaporation number
factor at `:4601-4603` is REAL32 and lacks the explicit finite/overflow checks
present in the melt transaction, but its `QG>qcrmin` guard keeps the
small-positive continuation branch out of that division.

This review establishes source-level formula domains only. It does not
establish runtime validity or scientific validation for the changed policy.
