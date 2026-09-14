# CP02 — candidate WPS creation without replacement

LAPSPREP already checks whether SHADOW output paths exist before analysis.
Its WPS writer still opened the final path with `STATUS='REPLACE'`, so a file
created after that check could be overwritten.

`output_ungrib_format` now accepts optional `create_new`; the actual non-OFF
SHADOW candidate call enables it. The final Fortran OPEN uses `STATUS='NEW'`.
The default remains the legacy writer behavior. No new writer wrapper,
metadata schema, or numerical formula was introduced.

Validation:

- Focused pinned Intel O0/O2 tests create a new file, reject an existing
  sentinel unchanged, and verify default legacy replacement still works.
- Fresh full O2 LAPSPREP and source/runtime-verified executions produced OFF
  and HYDRO WPS files byte-identical to the preceding accepted outputs.
- An actual preexisting-file case exited 1 at the earlier SHADOW preflight,
  preserved the sentinel, and created no diagnostic sidecar. It does not
  exercise the final OPEN race; the focused writer test covers that boundary.
- The one-off runner expected a later writer diagnostic and therefore exited
  1 after these actual runs. Its incorrect diagnostic expectation is retained
  explicitly in RESULT.json; it is not presented as a successful runner.

[Focused tests](../scratch/cp02_wps_writer_status.mfKBuf/RECEIPT.json),
[actual full-executable results](../scratch/cp02_wps_create_new.EsG4m1/RESULT.json),
[RED review](../scratch/cp02_lapsprep_pair_red_20260911/RED_REVIEW.md).

This closes the candidate WPS replacement race. WPS/diagnostic pair binding,
publication as one completed generation, and native mask/frame/mass readback
remain separate CP02 work. Failed private staging is not a completed product.
