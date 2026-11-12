# Background ice proposal boundary

This is a research proposal producer, not an independent source of PSD information.
No qualifying independent real background was found in the bounded inventory.
The executable and test fixtures are not a replacement for that missing input.

The manifest has `schema: background_ice_prior_v1`, `mass_basis: dry_air`, and six
file identities named `analysis`, `background`, `authority`, `mask`, `driver`,
`policy`. Each identity is an object with `path` and `sha256` strings. Paths must
resolve to unchanged files. Use absolute paths when invoking from another directory.

The authority JSON must contain:

| Key | Required value |
|---|---|
| `kind` | `prior_cycle_forecast` |
| `source` | Nonblank source label, at most256 UTF-8 bytes |
| `independence_attestation` | Explicit nonblank scientific lineage statement |
| `mass_basis` | `dry_air` |
| `cycle_start` | `YYYY-MM-DD_HH:MM:SS`, strictly before the analysis valid time |
| `analysis_sha256`, `background_sha256` | Exact corresponding manifest hashes |
| `microphysics_source_sha256` | Fixed CONTROL SHA `f391b211c6e111f92a7213cc5a651606ec6b5826a47063e3057ab2d819e9a595` |

These statements are caller attestations. Hashes, timestamps and source strings
do not establish scientific authority, build equivalence or independence by themselves.

Both native files use `MP_PHYSICS=37`, one matching `Times` record and native
float32 mass-grid QICE/QSNOW in kg/kg and QNICE in kg-1. The manifest declares the
dry-air denominator. The analysis additionally supplies float32 AL and ALB in
m³/kg. The background's SIMULATION_START_DATE, and START_DATE if present, match
the declared prior cycle. A restart whose dates do not satisfy this contract
requires an explicit, separately reviewed mapping; it is not silently accepted.

Exact coordinates XLAT/XLONG/HGT/ZNU/ZNW, projection attributes listed in the tool,
and available hybrid coefficients must match. Missing, packed, nonfinite and
default-fill coordinates are rejected. Grid equality is equality of this native
computational grid representation; it is not proof that meteorological states
at equal sigma indices have equal physical pressure or height. No regridding is performed.

The mask NPZ contains a nonempty binary `valid` array in `(z,y,x)` order and
`source_sha256` equal to the analysis file hash. The selected cells and all input
identities are recorded. Coverage of this mask is part of experiment design;
acceptance of a subset does not imply domain-wide acceptance.

The policy is the existing `initialize_model_moments.py` source-bound policy:
`declared_before_experiment=true`, MP_PHYSICS37, explicit moment bounds, thresholds
and number caps. It may restrict the fixed source ranges, not enlarge them.

Build the driver outside the checkout using `tests/intel_toolchain.sh`, then run:

```bash
python3 tools/propose_ice_background.py manifest.json proposal.npz receipt.json \
  --work-root /path/to/external/scratch
```

Both output names must be new and in the same existing parent directory. The
producer stages and reads back both files, syncs them, then links the receipt
first and syncs its parent before linking the proposal. The final proposal is the
commit marker. A receipt alone can be an interrupted publication; it is not a
valid result. Consumers must require both files and verify `proposal_sha256`.
An interruption is not promised to remove orphan temporary files or a prepared
receipt. Ordinary exceptions remove only names still pointing to this call's inode.

Generated proposal NPZ files carry `producer`, `producer_receipt` and
`producer_manifest_sha256` in addition to the existing qi/qs/ni/valid/source
contract. `initialize_model_moments.py` enforces the corresponding receipt and
records its identity. Place both files together when transporting them.

Use the generated NPZ identity for `ice_snow_partition` in the existing fresh-real
handoff manifest. The fresh producer must reproduce the exact analysis file SHA;
all other moments must still be completed. This boundary does not prove later
file→RK→KDM6 consumption, whole-domain energy closure or forecast skill.
