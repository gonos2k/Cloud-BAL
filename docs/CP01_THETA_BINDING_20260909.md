# CP01 native temperature mapping binding

The retained research-host input selects `USE_THETA_M=1`, both in its NetCDF
attribute and the executed `real/namelist.output`. This branch is known for
this artifact, not unresolved.

The two serialized temperature variables are different:

| Native field | Meaning | Source binding |
|---|---|---|
| `T` | dry perturbation potential temperature, `theta_d - 300 K` | Registry maps `th_phy_m_t0` to `T`; initialization saves dry `t_2` before conversion |
| `THM` | moist perturbation potential temperature, `theta_d*(1+(Rv/Rd)*rv)-300 K` | Registry maps internal `t` to `THM`; selected initialization branch converts it |

In the named source, `Registry/Registry.EM_COMMON:207-211` specifies the file
mapping. `dyn_em/module_initialize_real.F:4897-4915` preserves the dry field
and then converts the internal field. `share/module_model_constants.F` supplies
`T0=300`, `Rd=287`, `Rv=461.6`. Source, input, namelist and initialization
binary hashes are retained in the receipt below.

The source expression replayed with its float32 operation order is:

```
THM = (T + float32(300)) *
      (float32(1) + float32(float32(461.6)/float32(287))*QVAPOR) - float32(300)
```

All 2,573,532 cells match exactly. Replacing `Rv/Rd` with 1.61 mismatches
1,830,704 cells; treating dry T as THM mismatches every cell; a one-ULP THM
mutation is detected. The input file remains unchanged.

An initial float64-expression probe did not reproduce the float32 intermediate
rounding and exceeded a bound based only on final stored-field rounding. It
is preserved as `initial_probe.json`, but is not the successful oracle.
The final result has zero discrepancy and uses no relaxed tolerance.

[Receipt and reproducible oracle](../scratch/cp01_theta_binding_hgb_gam_/receipt.json)
bind the named stored-field mapping and declared branch. They do not establish
full source/build equivalence, native energy conservation or forecast skill.
Those limitations do not make the inspected file's temperature mapping unknown.
