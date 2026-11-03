# Bounded C2 replays, 2026-11-03

Pinned Intel ifx O0/O2 replays reproduced both retained local results. The first group cell (199,52,21) still rejects the REAL64 candidate at storage stage 2; the separate callback cell (2,219,13) still crosses the strict bound during independent REAL64 conversion. These are different cells. Exact classifications and callback bits match the retained results. No numeric policy or bound was changed, no new producer stencil was captured, and no H/A/N forecast was run. C2 remains incomplete.

See `validation.json` for commands, compiler/source pins, exact comparisons and the preserved initial /tmp execution-permission failure. All compilation ran in fresh scratch outside the source tree. Generated Fortran copies are evidence of the unchanged bounded diagnostic, not new production code.
