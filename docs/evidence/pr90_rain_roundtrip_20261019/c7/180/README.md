# C7 paired 180-second run receipts

This archive contains exact-byte copies of the OFF and COUPLED preflight and closed run receipts. Large native history and RSL payloads remain in their original `/var/tmp` run directories; this directory does not copy them.

Both archived receipts report `COMPLETE`, return code 0, and nine model timestamps from `2026-08-16_13:00:20` through `2026-08-16_13:03:00`. The final timestamp is the 180-second model endpoint. Each receipt binds its history output by path and SHA-256, the same candidate build receipt, and the same executable.

| Arm | Preflight SHA-256 | Run receipt SHA-256 | Bound history SHA-256 |
|---|---|---|---|
| OFF | `257e1e0144c895ef5912cb69d0315e6ef733454820744c77623749127548c064` | `3dc5773680fb0d92cbdf2aeb0a8ebaa1739e11c6366152add51e949c6f767ab1` | `46724cb66a4eaaaa9b543d6feb0c2e6035d6d779493858a684066d1a259522ba` |
| COUPLED | `4d738897a668276792c3f94ad28b25efc221f0c9a48837da561c0b840d4b27d4` | `72fe00aebe9db05270c747b974218114d3f3f83d1d7c6a87d4032b6399c5a0e0` | `8077b533c67c1c3202706a3aa572737db53d7af58a68ea3f2ef9866d4e77a261` |

Shared candidate bindings: build receipt SHA-256 `7a58ac2ae90eca9ffe0500515282b537e11db25ab9de8175856609bf812bba31`; executable SHA-256 `5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572`; KDM source SHA-256 `983095a0aa0c76eab4efdda27f9435e61634e08e542ef9bd096aa4cf8004eca4`; pinned Intel profile SHA-256 `5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4`.

The source build is a selected-object partial-host overlay, not a clean whole-WRF build. Receipt completion establishes this paired 180-second execution only; it does not establish physical validation or close the separate 600-second experiment.
