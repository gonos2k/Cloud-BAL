# PR83 team review and validation

Four focused workstreams used `gpt-6-luna` with high reasoning effort, within the four-agent limit. Root reviewed the integration and evidence. Review preceded commit and publication.

| Workstream | Reviewed result | Scope |
| --- | --- | --- |
| Moment policy | Actual-source Gamma coefficients, REAL32 dry carrier, native caps, atomic copy/rejection and manufactured positive copy | Research interior prior; no real initialized candidate accepted |
| Native initialization | Cold-start input transaction, shared runner/receipt handoff, isolation and initialization-versus-first-step gates | Retained partial host; no successful first microphysics call |
| Readback and OFF | Mask/fill rejection, receipt/file binding, MODE_OFF chain and signed same-grid inventory | Initial-output and transfer diagnostics |
| RK/evidence/KG | Ordered archive-member replacement, actual RK operands, compact archive bindings and guarded KG plan | Observer does not change arithmetic; graph is navigation evidence |

Review findings were addressed before publication:

- Density follows actual `AL+ALB` REAL32 carrier. WRF `T` is perturbation potential temperature; an earlier EOS assumption was corrected before final real-candidate evidence.
- Cloud generalized-Gamma coefficients and ice number-per-volume cap are distinct from public number-per-dry-mass units. The independent ice bound confirms the final units and 2,305 active failures.
- Paired inventory calls the baseline and analysis in the order that produces **Xa−Xb**. Exact center and staggered coordinate comparisons were added; legitimate hydrometeor differences are allowed.
- An OFF-directory field report contained the coupled input/output hashes. It is excluded and labeled exploratory; fresh actual OFF and coupled reports bind exact run-receipt/input/output bytes. A swapped-output regression rejects this mismatch.
- The 430-line OFF runner clone was replaced by a pinned thin wrapper over the existing common runner. Its later pre-refactor bytes are archived at their own hash. The executed OFF runner's original bytes are unavailable; the record does not equate them with that archive.
- Successful-prior receipt schema and filename now agree with the PR83 caller. The caller separately records initialization readback, runner return code, actual model return code and first-step gate. A mocked cross-module regression exercises initialization pass with model RC 128 and first-step rejection.
- RK archive order and unchanged member hashes are preserved. Actual compile/link inputs are captured before use, available module files are hashed, and the supported Intel `-real-size 32` spelling is used. Earlier exploratory builds are not the authoritative evidence.
- Two new OFF documentation artifacts were moved from the maintained checkout into the isolated worktree. No pre-existing source or runtime artifact was replaced; the maintained 627-entry inventory was restored and rechecked.

Validation binds the unchanged 1,845-file canonical snapshot whose pinned Intel launcher exited 0, followed by focused checks of later final helpers. The final tests cover valid and rejected moment copies, actual NetCDF missing values, receipt swapping, frame/cap checks, wrapper gates, RK trace placement and signed inventory. Actual stored OFF/coupled outputs were reread without rerunning models for the final helper changes. The compact archive's member hashes and CRC are independently checked.

No unresolved code/publication blocker remains in the reviewed scope. The **physical blocker remains explicit**: the current 13 UTC ice mass is incompatible with the declared source PSD and native cap, so the new candidate was not created or launched. First-call success, donor/boundary moments, physical-time budgets, native force/continuity assessment, observation validation and short-time scientific acceptance remain open. These are not waived by unit tests or graph freshness.
