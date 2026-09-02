# Operational-original versus diagnostic-patch comparison contract

## Purpose

`tools/prepare_operational_comparison.py` prepares comparison evidence without
changing an operational product.  The word **original** has one meaning in
this workflow:

> a separately archived product written by the operational KLAPS chain.

Canonical `background_*` fields and diagnostic proposal NetCDF files are not
operational originals or full candidate products.  This contract permits only
a clearly labelled field-level diagnostic patch; it never creates full-pipeline
candidate evidence.

Every valid-time/product comparison is a three-file transaction:

| Manifest entry | Required evidence label | Required origin |
| --- | --- | --- |
| `original` | `REAL_OPERATIONAL_ORIGINAL` | `ARCHIVED_OPERATIONAL_KLAPS` |
| `candidate` | `DERIVED_DIAGNOSTIC_PATCH` | `OPERATIONAL_COPY_WITH_CANONICAL_HYDROMETEOR_PATCH` |
| `operational_unchanged` | `OPERATIONAL_UNCHANGED` | `LIVE_OPERATIONAL_KLAPS_UNCHANGED` |

The archived and live operational inputs must be independent files whose
checksum-bound snapshots have the same SHA-256 digest.  The patch must also be
an independent file.  The archived product is bound by `SHA256SUMS`; the patch
is bound by `PATCH_RECEIPT.json` with
`receipt_type=LOCAL_DERIVATION_RECEIPT`,
`patch_operation=ABSOLUTE_REPLACE_DIAGNOSTIC_ONLY`,
`full_product_candidate=false`, and `mass_basis_resolved=false`.  This receipt
records a local derivation and is deliberately not a Cloud-BAL generation
manifest or committed operational product.

## Readiness gates

A manifest is `DIAGNOSTIC_PATCH_VALID_NOT_COMPARABLE` only when every declared
pair passes all structural gates. This status is not comparison readiness;
`algorithm_comparison_ready=false` and
`mass_basis_gate=BLOCKED_UNRESOLVED` remain fixed:

1. The three paths are normalized relative paths below `--artifact-root`.
   Symbolic links, hard links, shared inodes, parent traversal and any path
   component containing `bigfile` are forbidden.
2. All three file SHA-256 values equal the values recorded in the comparison
   manifest.  The original's `SHA256SUMS` and patch derivation receipt
   are separately checksummed and must bind the exact product path, digest
   and—for the candidate—byte size.
   The candidate diagnostic configuration must equal
   `radar-only-shadow-ifx-2026-v3`; substring matches are not accepted.
3. Embedded product valid times equal the UTC manifest valid time.
4. Complete field inventories and field shapes/dtypes are identical and the
   product-kind minimum inventory is present.
5. Grid dimensions and projection metadata are identical.
6. Levels, units and staggering metadata are identical.
7. Manifest wind-coordinate declarations are identical.  WPS declarations
   must also equal the wind-coordinate flag embedded in every record.
8. The archived original and live operational file are byte-identical.
9. Valid-mask hashes match for every numeric field; every requested plot field
   exists and has at least one common valid cell.
10. Every plot uses an explicit, finite fixed scale from the manifest.  A
    data-derived autoscale is never substituted.
11. Each `(product_kind, valid_time)` appears exactly once. No artifact path
    or inode may be reused by another pair, and WPS record identities must be
    unique within a product.
12. WPS source labels must be nonempty. Embedded WPS source labels and NetCDF
    authority attributes containing canonical, background, diagnostic,
    proposal, or synthetic authority are rejected.

The supported copied-file formats are:

- `LAPS` and `KLBG`: WPS intermediate version 5
- `MET_EM`: NetCDF met_em with `Times`, complete variable inventory and the
  required WRF grid/projection attributes. Exactly one `Times` record is
  required, even when repeated records carry the same text.

The current Cloud-BAL diagnostic NetCDF carries
`result_authority=DIAGNOSTIC_PROPOSAL_ONLY`; it is rejected if presented as a
`MET_EM` candidate. `CANONICAL_BACKGROUND` and equivalent background-only
authorities are rejected for the same reason.

## Manifest example

Paths are relative to the explicit artifact root, not to the manifest.

```json
{
  "schema_version": 1,
  "comparison_id": "case-20260816T130000Z",
  "pairs": [
    {
      "pair_id": "met-em-20260816T130000Z",
      "product_kind": "MET_EM",
      "format": "MET_EM_NETCDF",
      "valid_time": "2026-08-16T13:00:00Z",
      "original": {
        "evidence_role": "REAL_OPERATIONAL_ORIGINAL",
        "origin": "ARCHIVED_OPERATIONAL_KLAPS",
        "path": "archive/MODL/KLFS/NE57/DAIO/2026081613/met_em.d01.2026-08-16_13:00:00.nc",
        "sha256": "<64 lowercase hexadecimal digits>",
        "wind_coordinate": "GRID_RELATIVE",
        "attestation": {
          "format": "SHA256SUMS",
          "path": "archive/SHA256SUMS",
          "sha256": "<SHA-256 of archive/SHA256SUMS>"
        }
      },
      "candidate": {
        "evidence_role": "DERIVED_DIAGNOSTIC_PATCH",
        "origin": "OPERATIONAL_COPY_WITH_CANONICAL_HYDROMETEOR_PATCH",
        "path": "shadow/MODL/KLFS/NE57/DAIO/2026081613/met_em.d01.2026-08-16_13:00:00.nc",
        "sha256": "<64 lowercase hexadecimal digits>",
        "wind_coordinate": "GRID_RELATIVE",
        "attestation": {
          "format": "LOCAL_DERIVATION_RECEIPT",
          "path": "shadow/PATCH_RECEIPT.json",
          "sha256": "<SHA-256 of shadow/PATCH_RECEIPT.json>"
        }
      },
      "operational_unchanged": {
        "evidence_role": "OPERATIONAL_UNCHANGED",
        "origin": "LIVE_OPERATIONAL_KLAPS_UNCHANGED",
        "path": "MODL/KLFS/NE57/DAIO/2026081613/met_em.d01.2026-08-16_13:00:00.nc",
        "sha256": "<64 lowercase hexadecimal digits>",
        "wind_coordinate": "GRID_RELATIVE"
      },
      "plot_fields": [
        {
          "plot_id": "temperature-500hpa",
          "field": "TT",
          "indices": {"Time": 0, "num_metgrid_levels": 10},
          "scale": {
            "value_min": 230.0,
            "value_max": 310.0,
            "delta_abs_max": 5.0
          }
        }
      ]
    }
  ]
}
```

For WPS products, a plot entry uses `field`, numeric `level` and `scale`
instead of `indices`.

## Invocation and outputs

```bash
python3 tools/prepare_operational_comparison.py \
  comparison-manifest.json comparison-evidence \
  --artifact-root /path/to/isolated/KLAPS/workspace
```

The output directory must not already exist.  It is published by one atomic
rename and contains:

- `READINESS.json`: deterministic, machine-readable gate result
- `comparison_data/<pair>/<plot>/metadata.json`
- fixed-scale `original.npy`, `candidate.npy`, `delta.npy` and
  `common_valid.npy` arrays for each accepted two-dimensional selection

Comparison arrays are written only after **all** pairs pass.  On any missing
original, candidate, field or metadata mismatch, only `READINESS.json` is
written, `algorithm_comparison_status` remains `NOT_RUN`, and the command exits
with status 3.  A ready comparison remains non-operational evidence:
`algorithm_comparison_status` remains `NOT_RUN_FULL_END_TO_END` and
`promotion_eligible` is always false.

The attestations are local, checksum-bound evidence; they are not digitally
signed operational authority.  `READINESS.json` therefore records
`status_scope=STRUCTURAL_VALIDATION_OF_DIAGNOSTIC_PATCH_ONLY`,
`provenance_authority=LOCAL_ATTESTATION_BOUND_NOT_SIGNED`,
`certified_operational_provenance=false`, and never promotes a candidate by
itself.  It also records
`evidence_time_scope=CHECKSUM_BOUND_INPUT_SNAPSHOTS_NOT_LIVE_STATE`: the tool
does not mutate operational files, but it does not claim that a concurrently
managed live path remains unchanged after its validated snapshot was taken.

## Current 2026-08-16 inventory limitation

Archived operational LAPS/KLBG/met_em triads currently exist for 13, 14 and
15 UTC.  The 12 UTC inventory lacks the archived operational LAPS product.
The 12 UTC comparison must therefore remain `NOT_READY`; KLBG or met_em must
not be substituted for the missing LAPS product.  No full pipeline-generated
SHADOW LAPS/WPS or met_em candidate has yet been published.  Existing patches
may satisfy this diagnostic-patch contract but cannot satisfy a full-product or
algorithm-comparison contract.
