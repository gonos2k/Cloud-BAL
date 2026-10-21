# PR96-C1 native launch and closed-audit handoff

`launch_snapshot.json` is a timestamped launch record. It binds the three
600-second requests, actual run preflights, frozen runner and build, common
boundary/namelist, arm-specific input files, and metadata waiter. No closed
C1 receipt existed when this snapshot was made. It does not establish
later process presence, completed steps, endpoint validity, or physical
approval.

The live requests use the Lustre `runs_on_lustre` directories recorded in
the snapshot. The original C4 files and completed 600-second results remain
preserved. The preliminary dry CLI output directories and the wrapper
errors that refused their reuse were moved into `preflights`; those attempts
did not start a model. Each real forecast was then launched once in a fresh
directory.

`closed_audit_queue.py` is the exact source of the separately running local
waiter, not another forecast launcher. It polls only finalized receipt
metadata until all three requests have closed. It then verifies the C1
executable/build/profile, each arm's source/input identities, and requested
schedule before invoking the existing frozen PR93 arm auditor. Its result
directory is outside the source checkout and is recorded in the snapshot.

The waiter keeps procedural completion, generic Q/N/B, exact source
endpoint and 8-ULP active-ice policy results separate. Its overview is always
`REVIEW_REQUIRED`, with physical approval `FAIL_OPEN`. Publication commits
may advance the checkout HEAD; startup/end HEADs are reported and all seven
actual audit-reader source hashes must remain unchanged. An absent or
incomplete receipt cannot become a successful 600-second comparison.

When the three completed receipts are available, the existing response
analyzer can use the same C1 roots and executable explicitly:

```text
python tools/pr94_hydro_response.py \
  --off-run <OFF_600s_c1> --hydro-run <HYDRO_600s_c1> \
  --coupled-run <COUPLED_600s_c1> \
  --expected-executable-sha256 a714f00d3f81c0b47d94aef815f1f765ae48842e9de629cb869323ccfc22a96d \
  --output <scratch-response-directory>
```

That tool requires three completed 600-second receipts, the same model and
boundary, and the source-bound current-generation HYDRO input. Its
pressure/Phi/wind/cloud summaries use the existing fixed support and
buffers. They are descriptive comparisons, not a water/energy/mass–wind
closure or independent observation skill assessment.
