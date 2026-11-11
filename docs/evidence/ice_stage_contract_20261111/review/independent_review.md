# Independent source and evidence review

The pinned CONTROL source places the entry ice-number clamp before the first
ice slope consumer. Ice sedimentation and other source operations can change
the state before the first PSD block. The first slope bounds inverse lambda;
it does not repair ice number. The first two PSD gates use QI >= 1e-14,
whereas the third uses QI >= QMIN and NI >= NCMIN. The entry cap therefore
cannot be asserted at every later stage. The separate frozen-state and
whole-column descriptions preserve this distinction.

An initial review found that the stage audit checked the active PSD result
only for internal probe consistency, leaving an incorrect reconstructed number
or slope undetected. The revised audit checks wrapper products and compares
each recorded first slope and PSD output against the corresponding
source-extracted REAL32 oracle. Its manufactured boundary checks distinguish
direct equality at the limiter from whether exp(log()) reaches that value.

`python3 review/recount.py`, run from this bundle's directory, independently
confirmed finite probes, all 30 original-versus-instrumented terminal byte
comparisons, and stage and over-cap counts for the saved O0/O2 local columns.
The eight `test_cp02_ice_stage_*.py` unit tests also passed. These checks are
limited to the retained columns and their chosen parameters. File-derived
thermodynamics and density are proxies; the experiments do not establish the
first WRF microphysics state, forecast behavior, or initialization admission.
