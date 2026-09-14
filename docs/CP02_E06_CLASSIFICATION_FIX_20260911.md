# CP02 E06 — compiler observation classification fix

The verifier previously treated any observation kind other than `exec` as an
open. It now requires exactly `exec` or `open`, with the corresponding exec
or open syscall family. Both checks occur before result/classification filters.
The production Fortran code and publication algorithm are unchanged.

The existing regression suite adds two mutations with adjusted counters and
exact rejection-reason assertions: unknown kind and open relabeled as exec.
Private copies of real case12 O0/O2 bundles each passed **59 checks**, exit 0.
Independent RED also verified rejection of exec relabeled as open.

Historical published bundles pin the old validator and correctly rejected the
initial attempts at the version check. The successful tests used private
fixture copies with an explicit validator source rebinding; original
generations, receipts and the old freeze remain unchanged. No physics rerun
was needed.

- [Results and new source freeze](../scratch/cp02_e06_kind_fix_20260911/RESULT.json)
- [Exact source hashes](../scratch/cp02_e06_kind_fix_20260911/SOURCE_FREEZE.json)
- [GREEN review](../scratch/cp02_e06_kind_fix_20260911/GREEN_REVIEW.md)
- [RED review](../scratch/cp02_e06_kind_fix_20260911/RED_REVIEW.md)

This closes the malformed observation-kind defect in the focused verifier.
It does not reissue historical publication receipts or establish CP02's
remaining canonical-to-native mapping and coupled-physics requirements.
