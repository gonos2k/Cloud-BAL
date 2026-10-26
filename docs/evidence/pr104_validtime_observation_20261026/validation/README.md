# PR104 focused validation

The authoritative `final_v3` run passes 144 affected Python checks with unchanged source pins.
It covers candidate generation/reference regressions, explicit valid-time and
station coverage, and shared-runner preparation/finalization. It invokes no
compiler or model. Pinned C2 is reused without a rebuild.

The initial concurrent run is invalidated: source/test files changed during it,
and its already-loaded positive contract fixture preceded stricter frozen-pin
checks. Its failed result and changed-pin list are retained as development
history, not as validation of the final source. The final run starts after
source freeze. The earlier `final` directory records 143 checks before the
additional finite-observation guard; it is retained as an earlier source snapshot.
