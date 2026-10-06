# PR59 agent-team audit — 2026-10-06

## Review identity and scope

The independent reviews started from PR59 head
`17ac5e351f04975e8123319f373a127a09d82b68` and compared its changes with
`97478079859d759bef4fbc163f63a29092bd4c30`. Four lead reviewers covered
numerical physics/operators, receipt semantics, runner/writer integration,
and evidence/checklist claims. Graphify supplied affected symbols and paths;
source inspection and targeted execution established the findings.

## Findings and remedies

| Finding | Reproduction and limit | Remedy |
| --- | --- | --- |
| Ordered NaN pressure comparison traps before failure return | A direct `build_diagnostic_balance_operator` call with one quiet NaN aborted with pinned Intel `-fpe0`, exit 134. The ordering was inherited from the control builder; canonical pipeline validation precedes this call, so this is not evidence of an actual NE57 pipeline failure. | Check finite pressure before ordered comparisons in the shared geometry initializer. Test both public builders. |
| Hydrostatic input mask metadata is incompletely checked | Changing the group's temperature valid/quality/source units from `1` to `K` still passed the full file validator and retained `interior_hydrostatic_independently_validated=true`. | Require declared axes, unit `1`, unpacked representation, binary validity, canonical quality bits, and production source bits for copied inputs. |
| Cloud provenance accepts manufactured sources | A valid cloud bundle with `SOURCE_MANUFACTURED_TEST` passed its provenance helper. The production writer already rejects this bit in cloud fraction, cloud type and phase. | Reject the bit in these file checks, including phase-only presence evidence. |
| New thermodynamic assertions are omitted from the normal unit runner | The standalone runner passed, but the checked/optimized loop in `run_unit_tests.sh` did not include `test_thermodynamic_constraints`. | Register that test in the existing loop. Both affected runners now default to fresh `/var/tmp` scratch; the scratch-root override remains available. |
| KG cache and receipt have stale publication status | The Oct 2 receipt retains an early `NOT_PUBLISHED` entry and source/rename open items alongside its later publication PASS. The hot cache still leads with September evidence. | Preserve the historical receipt, add a dated reconciliation receipt/audit entry, and refresh session navigation without relabeling historical graph timestamps. |

The hydrostatic residual remains the signed interior thickness diagnostic
using all six dry-air species. These changes introduce no physical zero
threshold, new source, boundary flux, moment prior or omega target.

## Validation

The pinned Intel profile is `tests/intel_toolchain.sh`. Fresh `/var/tmp`
checked and optimized builds passed balance operator tests (including direct
NaN rejection), partial-face/adjoint tests, pipeline authority tests,
thermodynamic constraints and existing hydrostatic increments. The focused
thermodynamic runner passed after its scratch change. Shell syntax and
`git diff --check` passed; unit-runner registration was checked directly.
The complete default unit suite was not rerun in this follow-up.

Python validator regression tests, cloud provenance controls, and signed
hydrostatic receipt controls passed. The hydrostatic test now rejects sixteen
mutations, adding three mask-unit changes, packing and manufactured source
and an invalid mask in an otherwise empty assessment to the earlier ten.
The empty-assessment control remains accepted; present inputs are still checked.
Cloud tests include manufactured fraction/type and
phase-only evidence. Northern/southern Lambert tests passed against the
retained pyproj 3.7.1 / PROJ 9.5.1 environment; their implementation is unchanged.
The strengthened full validator also reopens the original published NE57
SHADOW without failures. Seventeen original positive writer fixtures pass
the hydrostatic helper, including no-change and transition cases.
Source and log hashes are recorded in
[the audit evidence](evidence/pr59_team_audit_20261006.json); full logs remain in
`scratch/audit_pr59_20261006/audit_receipt.json` in the review worktree.

## Evidence reconciliation and open conditions

The actual producer and research generation remain bound to code commit
`90179191edc33b5ae5606a37f4cd67eac507eed0`. `17ac5e3` added the evidence
documents; this audit adds later code and validator changes. The producer
was not rebuilt or rerun for these guard/receipt changes, and its generation
is not represented as a build of the new audit commit.

Independent hash checks matched the retained generation manifest
`95c55515e55960053ffae07c588d9b58c27cd1cb4b9e51dda4164f5881aac0c8`,
all three products, reopened readback, and six earlier validation logs.
The 391 captured build-input hashes establish their recorded membership
and bytes; they do not prove compiler-process closure.

The earlier Lustre transaction was NOT_PUBLISHED. The later local `/var/tmp`
research transaction was PASS and bound to `9017919`; its success supersedes
the earlier source-binding/rename open items only for that specific research
generation. The original KG receipt remains unchanged as historical evidence.

Independent source/boundary conservation, complete joint feasibility and
optimality, upstream-generation/compile closure, current-candidate
metgrid/real/native identity, KDM6 Q/N/QIB first-call traces, and the same-setting
BASE/HYDRO/COUPLED startup/forecast comparison remain open. The team found
no further verified blocker in the reviewed implementation after these fixes;
this does not grant physical, scientific or operational initialization approval.
