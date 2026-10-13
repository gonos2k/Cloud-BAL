# PR83 RK operand capture — 2026-10-13

The diagnostic build records the operands and result of the existing `rk_update_scalar` update at `(i,j,k)=(4,2,22)` for `p_qnc` (`im=3`). The observation patch only adds bit-pattern writes around the existing expressions. It does not change the update arithmetic.

The final guarded build used the pinned Intel `ifx` profile, included 640 `.mod` files found in the retained compiler include directories, retained `module_em.o` at its original archive row, and passed pre/post hashes for all recorded direct dependencies. The build receipt and exact command evidence are linked from [the machine-readable trace receipt](PR83_RK_OPERANDS_20261013.json).

| RK step | Captured advective product | `sc_tend` | `scalar_1` input | `scalar_2` input | `scalar_2` output |
|---:|---:|---:|---:|---:|---:|
| 2, second observed update | `8002413D` (−2.0707408e−40) | `00000000` | `00000000` | `00000000` | `80000010` (negative subnormal) |
| 3, second observed update | `000009D4` (+3.5256669e−42) | `00000000` | `00000000` | `80000010` | `00000001` (positive minimum subnormal) |

The captured `advect_tend` values were `800244AA` at RK2 and `000009E3` at RK3; both were multiplied by the captured `msfty=3F7E7D5A` (0.994100213). At both stages `sc_tend` was zero, so the recorded tendency equals the actual product. The traces therefore locate the requested zero → negative subnormal → positive minimum-subnormal transition in the update outputs and show the actual carrier, coefficient, and tendency operands used at each observation.

The run subsequently stopped with `KDM6 invalid NC number basis input`. This capture does not establish the specific reason for that later validation failure or validate any physical moment initialization.
