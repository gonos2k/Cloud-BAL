# PR93 freezing packet outcome contract

The retained helper's existing outputs already express the required three
outcomes:

| Case | `base_valid` | `accepted` | Meaning |
| --- | --- | --- | --- |
| Invalid active T24 ice base | false | false | Invalid base; the caller's invalid-base fatal applies. |
| Valid base, fixed packet below both donor half-ULPs | true | false | Deferred atomically; endpoints and approvals remain unchanged/zero. |
| Valid base, zero mass and number request | true | true | Accepted zero packet; endpoints remain unchanged and fraction is zero. |

Both KDM6 freezing call sites in the PR85 source patch fatal only when
`base_valid` is false. A valid deferred packet is written to the ledger and
does not enter that fatal path. No source API change is needed.

The captured T24 active-ice state has a promoted mean ice mass about 11
REAL32 ULP above its configured upper bound. The helper tolerance is 8 ULP,
so the T24 replay correctly remains invalid (`false,false`). Its donor values
and proposal are also tested with an empty ice category to isolate
representability: mass is 0.234157 cloud-q ULP and number is 0.125874 cloud-N
ULP. Since both requests are below half a donor ULP, halving any positive
`theta <= 1` cannot change either cloud donor. This valid-base fixed packet
therefore returns deferred (`true,false`) and leaves all four stored values
and approvals unchanged. The fixture passes the exact native cutoff expression
`NEAREST(1.e-14,-1.0)`.

The isolated donor proof does not reclassify the captured T24 production
packet: that packet still has an invalid active-ice base. See the
[evidence record](evidence/pr93_packet_contract_20261020/README.md) for
validation environment, hashes, and scope limits. Pinned Intel O0 and O2
fixture builds passed; no native integration run or scientific validation
was performed.
