# C15 T15/RK1 mixture witness replay

Status: **local trial replay closed; transaction commit unverified**. The paired native run had reached 280 seconds when the frozen T15/RK1 captures were supplied. This report makes no full-run completion or commit claim.

The original `strict_graupel_pair` and `store_graupel_mixture` helpers were extracted from the hash-pinned C15 `module_em.F` and replayed with the pinned Intel O0 and O2 profiles. O0/O2 output matched in each arm. Every captured candidate Q/B bit pair matches its D1 FULL stage2 record at the same cell and coordinate. Every replayed store is valid and strict; all 17 original candidate pairs are themselves strict-invalid, as expected for these stage2 witnesses. Captured weights, donor Q/B terms, rates, source values, bounds, and candidate/stored/delta bits are retained per trial in the arm replay JSON.

| Arm | Local trials | D1 FULL | Stage2 | Stage6 | Exact helper replay | D1 stage2 candidates matched |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| OFF | 6 | 7 | 6 | 1 | 6/6 | 6/6 |
| COUPLED | 11 | 12 | 11 | 1 | 11/11 | 11/11 |

Stage6 is the separate bulk-volume policy path and does not call the legacy mixture helper; its witness absence is expected. The six OFF and eleven COUPLED mixture records cover the corresponding D1 stage2 rows.

## Bound artifacts

- OFF frozen capture: `input/off_mixture_witness.raw`, SHA-256 `c8b40ea75bd1c4a33104b9c8a01fef1c03b7dc05856976be62f47f617955f1ab`.
- COUPLED frozen capture: `input/cpl_mixture_witness.raw`, SHA-256 `ff447cd18406ed03a926652dbc0e9c86f7bf9b5c5d69f8a5553a4055c4f0616e`.
- OFF replay: `off/replay.json`, SHA-256 `5e17483979f8354d052b05cab115a959b36143d6e935075d64900cba76d74fd1`.
- COUPLED replay: `coupled/replay.json`, SHA-256 `6955680de26caff8db06f06623115822c9db631c8ee3ed4fd4814cc1915f8510`.
- Combined summary: `summary.json`, SHA-256 `ac318fd111d389923f0ced4961f8d0a428503a680812b9ed9bd904663b5cb5bb`.

The replay validates the helper outputs for the captured local trial. A matching later committed endpoint and transaction event must be checked separately before claiming committed state.
