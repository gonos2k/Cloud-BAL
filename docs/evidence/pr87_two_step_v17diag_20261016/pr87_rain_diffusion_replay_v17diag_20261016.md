# PR87 rain diffusion precision replay (V17 diagnostic)

Target: timestep 2, RK1, rain pair p=3 at `(i,j,k)=(110,5,18)`; probe arrays use `(i,k,j)=(110,18,5)`. This is a one-cell offline replay of the captured active `horizontal_diffusion("m",...)` call.

## Evidence

- Actual V16 rain contract: `pidn=12566.37109375`, `power=3`, `lambda_min=961`, `lambda_max=35000`; strict mean-mass ratio bounds are `2.9309320335276967e-10` to `1.4159232646326343e-05`.
- The captured R32 diffusion producer starts from zero Q/N tendency. Its native R32 stencil replay matches the POST value bitwise for both QR and QNR. POST also matches the corresponding FULL `qs64/ns64` rate after R32 conversion bitwise; air rates at this cell are zero.
- Native R32 producer deltas: QR `5.7994551383444559e-08`; QNR `197.87068176269531`.
- Same active stencil evaluated in R64 from the exact captured R32 operands: QR `5.7994549786556961e-08`; QNR `197.87067140247404`.
- FULL candidate Q/N is `2.9309320040144683e-10`, below the native strict lower bound by `2.95132283e-18`. Replacing only the producer delta with its R64 evaluation gives `2.930932076770217e-10`, above the lower bound by `4.32425204e-18`. Both values are assessed using the same strict rain bounds.
- Coefficient mapping follows the pinned helper `name="m"` branch: x− uses `msfux(i,j)/msfuy(i,j)` and averages center/west `xkmhd` and `c1*MUT+c2`; x+ uses the same ratio at `i+1` and averages east/center; y− uses `msfvy(i,j)*msfvx_inv(i,j)` with center/south averages; y+ uses that metric product at `j+1` with north/center averages. The outer terms are `msftx*msfty*rdx` and `msftx*msfty*rdy`. Each captured operand was read from the matching stencil location.
- Helper procedure SHA256: `cbcc347345a6449b9e5666407c5ef8c6a0db73a9a397d0e306ad14a085783ac3`.

## Scope

This supports a source-precision cause at the selected cell and identifies R64 tendency production as a targeted candidate. It is not a whole-run validation or a two-valid-step pass. The V17 diagnostic overlay is a partial native overlay, not a clean build; no floors, bound changes, or full stdout/large arrays are included here.

Receipt hashes and the four selected PRE/POST stdout rows are in the adjacent binding JSON and tagline text file.
