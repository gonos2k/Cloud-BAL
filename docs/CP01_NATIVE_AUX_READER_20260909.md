# CP01 native-file auxiliary inspection — 2026-09-09

`tools/check_native_mp37_aux.py` reads a single-time MP37 `wrfinput` file and
passes its five auxiliary fields and four hydrometeor mass fields to the
existing diagnostic validator. This replaces ad hoc array extraction with a
reusable native-file inspection entry point.

The reader requires the native dimension order
`Time, bottom_top, south_north, west_east`, exactly one time record, and
MP_PHYSICS=37. Missing fields, masked fill values, incompatible dimensions,
nonreal/negative/nonfinite arrays and read failures reject. Malformed payloads
are checked before missing physics or denominator declarations can hide them.
It does not infer a denominator from a variable name or a unit string.

Complete payloads still return NO_AUTHORITY: the reader has no authenticated
denominator/startup binding. Its JSON reports contain `accepted=false`,
`native_authority=NONE`, `promotion_eligible=false` and `inspection_only=true`.
Exit 3 means NO_AUTHORITY; exit 2 means REJECTED. There is no model-launch,
approval-override, native write or positive execution-authorization branch.
Reports go to stdout so the reader cannot overwrite its input with a report.

Example:

```bash
python3 Cloud-BAL/tools/check_native_mp37_aux.py /path/to/wrfinput_d01
```

The file is opened read-only, and its content hash is compared before and
after inspection. This detects a changed file during the probe; it is not
an atomic future-launch or producer-authentication guarantee.

## Existing execution boundary

The retained `scratch/native_handoff_stage.ymn6MM/run_native_handoff_preflight.sh`
is a historical source/hash-bound metgrid/real execution script. It checks
existing-output absence and manifests, but does not implement the MP37
auxiliary contract or launch a forecast. It is preserved as historical
evidence. No maintained production native writer/launch integration point
was found among the current Cloud-BAL tools and tests.

Source trace: Cloud-BAL's `output_ungrib_format` in
`src/lapsprep/module_lapsprep_wps.f90` writes WPS intermediate data, without
MP37 auxiliary arguments; the external host's `main/real_em.F` writes native
`wrfinput_d01`. LAPSPREP checks the WPS writer's failure status, but the writer
opens with `STATUS='REPLACE'` and has no rollback for a mid-write failure.
The separate `tools/cloud_bal_transaction.py` publication machinery currently
serves SHADOW diagnostics. Neither mechanism establishes an atomic native
handoff. This existing WPS transaction limitation is recorded, not repaired
by the read-only auxiliary reader.

This step therefore establishes the native-file-to-validator connection,
not native handoff enforcement. The next integration needs an identified
maintained launch/write boundary and authoritative denominator/startup
evidence. CP01 remains IN_PROGRESS / NOT_RUN.

## Actual-input result

The retained 13 UTC input produces NO_AUTHORITY (exit 3), with the same
positive-mass/zero-moment counts as the previous array probe: cloud 962388,
ice 258832, rain 219996 and graupel 817. Input SHA-256 remains
`f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1`.
The counts are observations, not a prescription for filling number fields.

## Validation

[Receipt](../scratch/native_aux_reader_m44m_vlj/receipt.json): twelve file-based
tests pass for payload decoding, cell counts, physics metadata, fill masks,
missing fields, reordered dimensions, empty/ambiguous time, invalid physical
values, unreadable files, JSON exit statuses and byte preservation. The
reader test is registered in `tests/run_python_contract_tests.sh`; this step
ran the focused tests, not the entire portable suite. Source snapshots and
hashes, the actual-input exit-3 report and execution log are retained beside
the receipt. No Fortran build or native model execution was performed.

[Independent review](../scratch/native_aux_reader_m44m_vlj/independent_review.md)
checks the frozen source, test log and actual-file report. It confirms that
`native_enforcement` remains false. The Cloud-BAL
[graph receipt](../scratch/native_aux_reader_m44m_vlj/kg_receipt.json) records
3721 nodes / 7918 edges / 244 communities; parent-graph freshness and native
authority are separate.
