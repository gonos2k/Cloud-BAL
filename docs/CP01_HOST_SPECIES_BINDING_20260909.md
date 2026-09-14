# CP01 host and species binding — 2026-09-09

Status: CP01 scoped contract review complete. The [exit matrix](CP01_CONTRACT_EXIT_MATRIX_20260909.md)
controls whole-CP01 disposition. This contract does not authorize a model launch.

## Selected research profile

The selected host is KIM `KIM_RDPS_MODL_V2026.2`, labelled WRF 4.6.0.
The retained runtime reports `861c8d4d8aba5e4b13148cb15b4c171746edc6ca`;
the currently inspected dirty source checkout is
`24e82afde6f9cb4b299ee330643253fbbc565a79`. Individual source hashes,
rather than either commit label alone, pin the explicitly private
corrected MP37 interface described in the
[private host profile](CP01_PRIVATE_HOST_PROFILE_20260909.md).
Its machine-readable artifact bindings and five-field startup policy are in
cp01_private_host_profile.json (로컬 전용 자료: `../config/cp01_private_host_profile.json`; 공개 PR에 포함하지 않음).
The private profile retains the full host and its reused dependencies;
the internal five-source wrapper is a separate bounded conversion test.
Neither is declared equivalent to the KLFS operational binaries.

The retained research case is `2026-08-16_13:00:00`, C-grid, `e_we=235`,
`e_sn=283`, `e_vert=40`, `dx=dy=5000 m`, `p_top=5000 Pa`, `HYBRID_OPT=2`,
`MP_PHYSICS=37`, `USE_THETA_M=1`, `use_sh_qv=true`, time step 20 s and
specified boundary width 5. Scalars use mass points; U/V are horizontally
staggered and W/PH use vertical faces. Boundary and frame restrictions are
in the [mass/frame binding](CP01_MASS_FRAME_BINDING_20260909.md).
The private 20-second forecast probe instead used manufactured periodic X/Y
boundaries, separately bound in the profile manifest. Its success does not
validate the staged case's specified boundaries or their physical authority.

| Binary role | SHA-256 | Scope |
|---|---|---|
| Staged research real | `fa76d4bb17c0c63ecfed12a09ed912ba149248c1378f45b1938b16d2f729bdff` | Input producer identity |
| Private corrected forecast host | `583a9c628a3677fe699ad255b6772feca1c301c46d875d0b9e32dfa2bfd2cc1c` | Selected private profile; no operational equivalence |
| Historical source-tree forecast baseline | `1f2dcb2a59f0a4774ed9a2026de5f6f3841acf7e607bfdae92247cf60833d517` | Comparator only |
| KLFS operational init | `49e5d54c58259baa21a07899b56af10ed67f56925f829bd7b5beb04a00e5fbf2` | Separate inventory |
| KLFS operational forecast | `c956cdcb352d7a5cc8de4092e5a5103c41dd168b4f684c56b30ba8b05c84f9d9` | Separate inventory |

## Variables, basis and startup coverage

Canonical water fields `rv, rc, rr, ri, rs, rg` map by name to native
`QVAPOR, QCLOUD, QRAIN, QICE, QSNOW, QGRAUP`, all kg/kg dry air.
The WPS writer emits `QC/QI/QR/QS/QG` for hotstart and direct `QV` when
supplied. Its RH-only legacy interface does not establish a zero QV.
WPS has no QN/QIB or native vertical-wind payload.

| Native auxiliary | Selected public unit/basis | Startup contract |
|---|---|---|
| QNCCN | number/kg dry air | Configured CCN number/m3 converted with `al+alb`; separate source-bound startup rule |
| QNCLOUD | number/kg dry air | No implicit initializer; external bound producer declaration required |
| QNICE | number/kg dry air | No implicit initializer; external bound producer declaration required |
| QNRAIN | number/kg dry air | No implicit initializer; external bound producer declaration required |
| QIB | m3/kg dry air | No implicit initializer; external bound producer declaration required |

The corrected KDM6 wrapper converts public number/kg dry air to internal
number/m3 using dry density on entry and reverses the conversion on exit.
`moist_physics_prep_em` resets the density to `1/(al+alb)` before the
microphysics driver passes `DEN=rho`; an earlier physics routine's moist-air
density is a different stage. Registry unit strings alone are not this basis
proof. The explicit selected implementation and call order provide the contract.
The [internal O0/O2 wrapper probe](CP01_QN_WRAPPER_PROBE_20260909.md) is a
bounded conversion check, not a full host conservation result.

All five auxiliaries are required for MP37 coverage. The four positive
hydrometeor mass/zero-moment pairs are checked cell by cell. A missing field,
malformed payload or bad units must reject; unknown or mismatched basis and
unverified startup authority must prevent handoff. No number concentration,
graupel density prior or missing volume is fabricated. Numerical zero-volume
legacy equivalence and physical startup authority remain distinct claims.

## Retained input and execution boundary

The retained wrfinput SHA-256 is
`f0ccee31f6f7214c9d7b5ccf19e0ae55d9fe43751e0fcffbcaedfc6080a052e1`.
All five auxiliaries are zero. Positive-mass/zero-moment counts are QCLOUD
962388, QICE 258832, QRAIN 219996 and QGRAUP 817. This input remains
`NO_AUTHORITY`; documenting the private profile does not repair the payload.

The maintained native-file inspector and preflight coordinator are in
[check_native_mp37_aux.py](../tools/check_native_mp37_aux.py). The coordinator
validates bytes directly before starting an output transaction. Invalid or
unauthoritative input cannot replace the previous committed generation through
this coordinator. A constructed structural-positive case may publish only a
labelled diagnostic receipt; authenticated native launch permission is absent.
This boundary is not a full WPS/native writer or forecast launcher.

Pressure-fixed diagnostic mass and native dry mass remain separate as defined
in [NATIVE_MASS_FRAME_CONTRACT.md](NATIVE_MASS_FRAME_CONTRACT.md), including
named A_Q/A_M/A_E units and conventions. Full native roundtrip, continuity,
energy conservation and operational equivalence remain CP02/06/07 work.

Historical baseline investigations, rejected priors and chronological test
receipts remain in the [execution record](CP01_EXECUTION_RECORD_20260907.md).
The prior inventory revision is preserved in
`scratch/cp01_final_binding_vpoe3vby/host_species_binding_before.md`; its
unresolved-source statements describe the earlier baseline, not a silent
change to the selected private profile.
