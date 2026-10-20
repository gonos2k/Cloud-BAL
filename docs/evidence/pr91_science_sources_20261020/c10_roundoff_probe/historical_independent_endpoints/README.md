# Historical manufactured case (superseded)

This preserves the first counterexample, which independently set `t_after32=0` despite `t_before32=1` and `Dold64=2^-54`. It demonstrated cancellation for independent inputs, but did not establish the ordinary producer rounded-addition relationship. The primary probe one directory up replaces it with `t_after32=REAL32(t_before32+Dold64)` and is the case to cite. This historical result remains manufactured and is not actual model failure evidence.
