# PR93 publication preflight review

**Disposition: one wording blocker before publication; remaining inspected claims are scoped and evidence-bound.** Read-only review of PR93 source, test, documentation, and evidence metadata. I did not read active bound-run payloads, launch a model, or run optional tests.

## R32 ICE export and packet outcomes

- The selected C4 source and source review identify the ICE host export as `volume_number_to_specific(Nvol,rho,Nspec)` and KDM6 reentry as `specific_number_to_volume(Nspec,rho,Nvol)`. The current producer fixture exercises that REAL32 roundtrip through the unchanged freezing consumer. It keeps the common-core REAL64 `Nspec64=Nvol/rho` store test separate and explicitly does not call it the native ICE export or a complete host transaction.
- The focused validation manifest binds the current Python test driver SHA `b107a9a3…1c194d84`. The fixture receipt binds generated Fortran SHA `1cd73963…f4238cfa` and generated source SHA `73db5c6a…f1bed833`; both pinned Intel O0/O2 receipts include the native ICE roundtrip and separate R64 component pass lines.
- The packet docs correctly distinguish the captured T24 invalid base (`false,false`) from the valid-base donor-isolation case that defers the tiny fixed packet (`true,false`). The producer fixture’s repaired active-ice R32 roundtrip also remains valid and defers the fixed packet without endpoint changes. None of these fixture outcomes claim that the captured invalid T24 production call was deferred.

## Runtime and science scope

- The active candidate binding is `PAIRED_600S_BOUND_LAUNCH_IN_PROGRESS` with scientific approval `FAIL_OPEN`. The earlier one-step launch is preserved as `INCOMPLETE`; the publication text says final runtime results follow only after both collectors close. I did not inspect active run payloads or infer their state.
- The QC report’s stored-time and mask statements match its bound evidence and the earlier scoped QC review. It does not claim a complete 600-second history, observation skill, causal QC-only effect, or mass/energy closure.

## Blocker

`docs/PR93_ACTIVE_ICE_CONTRACT_20261020.md` says “Native stage checks cover the actual integrated path.” At this preflight, the paired bound runs are still marked in progress and have no final receipts; the preserved one-step failed launch does not establish T24/native end-to-end behavior. The fixture validates the R32 conversion/consumer component path, not the complete native host transaction. Reword this sentence to state that native integration coverage is pending both bound receipts, and keep the fixture’s component scope explicit. No other concrete publication blocker was found in the inspected material.

## Resolution before runtime closure

Root replaced the premature integrated-path sentence with an explicit pending
bound-collector/stage-audit statement. The component/native distinction is now
preserved. Actual final execution claims require the later closed-run review.
