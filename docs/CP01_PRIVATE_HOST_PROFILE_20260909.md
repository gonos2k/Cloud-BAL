# CP01 private corrected KDM6 host profile

Date: 2026-09-09

The authoritative research profile is
`config/cp01_private_host_profile.json` (로컬 전용 자료: `../config/cp01_private_host_profile.json`; 공개 PR에 포함하지 않음).
It binds the selected private KDM6 host, corrected source patches, private
objects, executable, startup input, compiler profile and the five-field
auxiliary contract. The profile is scoped to CP01. It excludes a full native
writer, round-trip forecast work and CP02/CP07 operational claims.

The profile pins the public auxiliary basis to dry air. `QNCCN`, `QNCLOUD`,
`QNICE` and `QNRAIN` are `number kg-1 dry air`; `QIB` is `m3 kg-1 dry air`.
The corrected wrapper converts public number fields to KDM6's internal
`number m-3` representation with the call density and converts them back on
return. The call-order binding is explicit: `solve_em.F` resets `rho` to
`1/(al+alb)` before the MP37 driver passes `DEN=rho`; `al+alb` is the dry
specific volume used by the CCN startup conversion.

`QNCCN` has one configured initializer. The Registry defaults are `ccn_conc =
1.0e8 number m-3`, `scale_h = 750 m`, `qnn_land_mult = 50` and
`qnn_sea_mult = 0.5`. The private `start_em` patch applies the altitude and
land/sea profile in `number m-3`, then multiplies by `al+alb` to serialize
public `QNCCN` as `number kg-1 dry air`. These values are source-bound
configuration values; they are not invented fallback values for the other
fields.

`QNCLOUD`, `QNICE`, `QNRAIN` and `QIB` are `NO_IMPLICIT_INITIALIZER`.
Each requires an externally bound producer that supplies the declared dry-air
denominator, units, shape, time and field identity. Missing or unbound
authority is `NO_AUTHORITY`. The profile forbids deriving a number field from
mass without a named producer, deriving QIB from mass with an unnamed density,
or treating a serialized zero as authorization. Every mass/moment pair is
checked cell by cell; positive mass with zero moment is `NO_AUTHORITY`.

The retained 13 UTC input is deliberately still invalid for handoff. Its
SHA-256 is
`f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1`. The
read-only inspection finds 962388 positive-QCLOUD/zero-QNCLOUD cells, 258832
positive-QICE/zero-QNICE cells, 219996 positive-QRAIN/zero-QNRAIN cells and
817 positive-QGRAUP/zero-QIB cells. All five auxiliary arrays are finite zero
over 2573532 cells. The profile does not fill these values, and the input
remains `NO_AUTHORITY` with exit status 3.

The binary identity is concrete but deliberately qualified. The pinned
executable is
`583a9c628a3677fe699ad255b6772feca1c301c46d875d0b9e32dfa2bfd2cc1c`; its
private `start_em.o`, KDM6 source/object, patched archive, namelist and input
hashes are listed in the manifest. The build used the pinned Intel profile
`Cloud-BAL/tests/intel_toolchain.sh` with ifx 2026.0 and Intel MPI 2021.18.
The pinned namelist has `periodic_x=.true.`, `periodic_y=.true.` and
`spec_bdy_width=5`; the staged manufactured input is therefore a periodic
startup probe carrying a specified-boundary width setting, not a physical
specified-boundary forecast test.
The link inserted corrected objects into a reused historical host archive and
reused historical main and external dependencies. Consequently
`legacy_operational_equivalence` and clean full-host build equivalence remain
false. The prior one-rank 20-second run is retained only as scoped CCN startup
evidence; it is not a physical-boundary, restart, science or operational
acceptance result.

The manifest therefore closes the CP01 research contract definition and its
fail-closed status for unbound startup data. It does not claim that an
authenticated external producer exists for the four uninitialized fields, nor
that the current native writer or production launch path enforces this profile.
