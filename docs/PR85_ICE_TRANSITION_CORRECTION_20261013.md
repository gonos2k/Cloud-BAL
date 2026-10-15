# PR85 correction: KDM6 ice-to-snow size transition

This dated interpretation record corrects the PR84 statement that the KDM6
200 µm ice-to-snow branch is unreachable. The retained PR84 receipt remains
unchanged; its `181.7 µm` value came from an incorrect evaluation of the source
expression.

The pinned consumer source is
`/var/tmp/pr84_ice_entry_guard_final_1efgtcsn/compile/module_mp_kdm6.F`, SHA-256
`f7fb216c82822162c30148829f207deeee5900e46e01ad9082ac58c802a181d9`. It sets
`dmi=3`, `mui=0`, `lamdaimin=9.08e3`, and `lamdaimax=1.82e6`. `slope_kdm6`
derives the ice slope from QI and NI and clamps it to those configured limits.
The mean-diameter expression used by the transfer branch is
`rslope_i*(Gamma(4)/Gamma(1))**(1/3)`. Since `Gamma(4)/Gamma(1)=6`, the
largest diameter admitted by the minimum slope is
`6**(1/3)/9080 = 200.123413307504 µm`, which exceeds the 200 µm threshold.

The transition can therefore occur for slopes from 9080 through approximately
`6**(1/3)/(200e-6) = 9085.602964160698 m-1`, subject to REAL32 evaluation of
the source expressions. The source `qmin` is a scalar routine argument; the
fixture uses `1e-14` so its positive-QI cases satisfy the guard. In the source,
colder-than-freezing ice (`T < 273.15 K`) with `QI >= qmin` and
`avedia >= 200e-6 m` enters the existing branch, which adds all remaining QI to
snow mass, then sets QI and NI to zero. It does not transfer ice number to snow
or change temperature. This is a runtime microphysics transition governed by
the diagnosed PSD and temperature, not a static species-remapping policy.

The focused regression in
[`test_pr85_ice_transition_regression.py`](../tests/test_pr85_ice_transition_regression.py)
extracts the pinned source statements for slope diagnosis, the preceding ice
sedimentation updates, mean diameter, and the existing transition branch. It
compiles and runs those statements with the pinned ifx profile at O0 and O2 in
fresh `/var/tmp` directories. The checked-in
[`pr85_kdm6_ice_transition_source_form.F90`](../tests/fixtures/pr85_kdm6_ice_transition_source_form.F90)
is the explicit source-form fixture used by the canonical unit launcher; its
SHA-256 is `06a985ba7f85268fbf6dab5b76adfe2c32f080807744aded8e27c1b5bb825f3c`.
When the pinned external source is available, the focused tool re-extracts the
same statements and requires byte identity with that fixture. It checks QI,
QS, and NI before and after the transition for slopes at 9080 and 9085.5 m-1,
plus a no-transfer case at 9085.61 m-1. The test is a focused source-form
regression, not a full KDM6 model call or a scientific validation.

Graphify was queried as navigation. The maintained worktree graph did not
expose this external KDM6 source path, so it could not validate the expressions;
the pinned source and compiled regression are the evidence. No graph update or
wiki write was performed in this scoped task.
