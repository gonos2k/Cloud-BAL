# CP02 producer continuation with enforced executable identity — 2026-09-10

Whole CP02: **IN_PROGRESS / NOT_RUN**. This increment applies the verified
main-ELF launch mechanism from
[the remediation record](CP02_REVIEW_REMEDIATION_20260910.md) to a new private
13 UTC cloud → humidity → derived execution. The retained wind → surface →
temperature inputs remain identified historical artifacts; their original
launches are not retrospectively bound by this run.

## Entry and required evidence

The parent entry record is `scratch/cp02_bound_followup__j5r2y3c/`.
It verifies the previous durable input snapshot's 102 files against its recorded
inventory. The original LMR CDL also matches SHA256
`a252465d690d1eef1b8e53364c3cdde9f612fd2a01a0f54f93a67c7e637bfad1`.
The new declared input bundle includes that template's bytes before the first
producer runs, and prepares all required output directories in fresh scratch.

Each producer requires a fresh pinned Intel build, input/runtime manifest
verification, and the generated `run_verified.sh` launcher inside the private
Landlock boundary. The same attempt must record the expected executable hash,
`BOUND_EXECUTABLE_READY`, process exit, producer completion marker, and validated
new outputs. Readiness alone is not completion. Source/configuration snapshots,
ordered timestamps, and pre/post inventories distinguish new outputs from
inherited products and record the permitted humidity PBL auxiliary rewrite.

Historical evidence and operational files remain outside the writable runtime.
Producer pathname writes are confined; stdout/stderr descriptors opened for
owned evidence logs remain separately writable. The main ELF is sealed, but
the controlling scripts/interpreter/environment are trusted and the dynamic
loader, libraries, helper binaries, and complete consumed-input read closure
are not thereby sealed.

## Scientific and checkpoint scope

Raw fill/missing counts and `valid_range` masking are recorded separately.
The previously observed LT1/LH3/LMR/LMT range metadata and inherited PBL
navigation gaps require source/units reconciliation. This execution preserves
the original fields and contracts; matching hashes or finite values do not
establish scientific validity.

This is one 13 UTC continuation. Full ordered-generation/read closure, all
four 12–15 UTC cases, balance/LAPSPREP ABI closure, durable publication and
native/scientific acceptance remain separate requirements. Full native
expansion continues to follow CP06-A.

## Result

Independent GREEN/RED result: **bounded execution PASS**. The consolidated
producer receipt is
`scratch/cp02_bound_followup__j5r2y3c/producer_chain/BOUND_CHAIN_RECEIPT.json`
(SHA256 `e34a0372ff060484086538c17c63489cbf2cfaa52551d21bed59ef36c9f3d40d`).
All 203 entries in its evidence manifest verify; the historical 179-file seal
also still verifies. The independent RED report is
`scratch/cp02_bound_followup__j5r2y3c/red_review.md`, and parent checks are in
`parent_seal_verification.json` in the same directory.

The three new producer executions completed with exit code 0 and their
same-attempt bound-executable and producer-success markers. The declared input
snapshot contains 103 files, including the original LMR template bytes.

| Stage | New outputs | Changes to pre-existing runtime files |
|---|---:|---|
| Cloud | 4 | None |
| Humidity | 3 | Declared `lapsprd/lpbl/pbl_depth.lpbl` rewrite only |
| Derived | 14 | None; LMR completed on the first attempt |

The parent independently checked all 21 durable products: receipt hashes,
2026-08-16 13:00 UTC valid/reference time, complete dimensions, and navigation
grid all pass. Every product is **byte-identical to the earlier continuation**;
all raw variable arrays also match, with no raw nonfinite numeric field found.
This establishes reproduction across the new build/launch path for this case,
not scientific validity. Evidence:
`scratch/cp02_bound_followup__j5r2y3c/parent_product_verification.json`.

## Metadata investigation

The parallel read-only investigation traced the attributes to the runtime CDL:
the Fortran writer's `units` argument is not passed through the C writer, so it
cannot override the CDL units/ranges. Source and output units agree for the
fields examined; changing data units is not justified by the reader masks.

- LT1 `t3` is Kelvin data with `[0,100]` range metadata. Its observed finite
  values are approximately 199–308 K.
- LH3 `rh3/rhl` are percentage data explicitly clamped to 0–100 in the source,
  but the CDL declares `[0,0.1]`.
- LMR `r` and LMT `llr` are dBZ, and LMT `lmt` is meters, yet all have the
  same `[0,0.1]` range despite their different units. Radar base/missing-value semantics and
  formal physical validation must be handled separately.
- PBL's C writer deliberately skips static navigation loading, expecting the
  CDL to populate navigation; the selected PBL CDL omits those data values.

Source/CDL citations, exact raw values and bounded remediation options are in
`scratch/cp02_bound_followup__j5r2y3c/metadata_review.md` and
`metadata_evidence.json`. This run retains the existing metadata for a direct
reproduction comparison. Correcting the authoritative templates/writer and
validating consumer behavior is a separate next increment; it does not require
inventing a unit conversion or accepting fields merely because masks disappear.
