# PR93 freezing packet outcome contract

This evidence covers the status contract of the existing
`pr85_kdm6_freezing_packet` helper. It does not change the helper or KDM6
source.

## Outcomes

| Case | `base_valid` | `accepted` | Meaning |
| --- | --- | --- | --- |
| Invalid active T24 ice base | false | false | Invalid base; KDM6's existing caller error applies. |
| Valid base, fixed packet below both donor half-ULPs | true | false | Deferred; stored endpoints and approved amounts remain unchanged/zero. |
| Valid base, zero mass and number request | true | true | Accepted zero packet; endpoints remain unchanged and fraction is zero. |

Both KDM6 freezing call sites in the PR85 source patch error only when
`base_valid` is false. A deferred packet (`base_valid=true`, `accepted=false`)
is ledgered without triggering the invalid-base fatal. No caller fatal was
found for this result.

## T24 boundary proof

The first case replays the captured T24 active-ice base and exact native
inactive cutoff expression `NEAREST(1.e-14,-1.0)`. The base fails the strict
active-ice cone by about 11 REAL32 ULP at the upper mass bound, beyond the
helper's 8-ULP cone tolerance. Its result remains `false,false`.

The second case keeps the captured T24 cloud donors and proposal values but
uses an empty ice category so the base is valid. This isolates packet
representability from the captured row's independent invalid ice base. The
mass request is 0.234157 cloud-q ULP and the number request is 0.125874
cloud-N ULP. Both are below half an ULP at their donors. Halving a positive
proposal cannot make either donor endpoint change; the fixed packet therefore
cannot be committed for any searched `theta <= 1`. It returns
`base_valid=true`, `accepted=false`, and rolls all endpoints and approvals
back to the input values.

This boundary proof is not evidence that the captured T24 production call had
a valid base. That captured call remains classified as invalid at the active
ice cone. The separate producer investigation is needed to classify the
earlier state before T24.

## Validation

`tests/test_pr93_freezing_packet_contract.py` compiled and ran the fixture in
fresh `/var/tmp` build directories with the pinned Intel `ifx 2026.0.0`
profile from `tests/intel_toolchain.sh`, at both O0 and O2. Both runs printed
`PR93 freezing packet contract cases PASS`. The compiler emitted warning
`#5194` for a generated preprocessed include line containing a long absolute
path; the fixture itself has no lines longer than 132 columns and both
executables passed.

SHA-256:

- Existing helper: `64daa2b447d39114affa944966b055d52c83fea8a4a208095c2fa9254f357a6a`
- Fixture: `70d76e05d9c8167e940726ed522fab53eaf3a85dd32c4d8b1f1e8fcb32415e6f`
- Test driver: `029db63b2ef9b5277b68f705134ff7f43b46221a1137164d30aa89969efc3972`
- O0 compiler log: `6ff15173dda4c91138c225ce8f996a999a88f925a663a7393237ef7e2fc1ec70`
- O2 compiler log: `3343cdb6366426eaa1f3641888f3b8ec46152149a397c92232ba82d08f289ba3`

The fixture verifies helper behavior and REAL32 representability. It does not
constitute a native KLAPS integration run or scientific validation.
