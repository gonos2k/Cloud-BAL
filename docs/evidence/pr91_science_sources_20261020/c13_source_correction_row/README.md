# C12/C13 FogDES source-correction row comparison

Compared the single `PR87_FOGDES_SOURCE_CORRECTION_RK` row with `source_step=3, i=162, j=132` from the closed C12 COUPLED gzip ledger and a bounded C13 COUPLED live-ledger prefix. The match has `changed_count=11` and `sample_k=1` in both.

The printed correction factor is positive in both rows. C12 reports `theta=0.0029400507919490337`; C13 reports `theta=0.0029400505591183901`, a decrease of `2.328306436e-10` (`7.91927e-6%` relative to C12). The row’s incoming aggregate and sampled-input fields are text-identical. The theta and all reported outgoing aggregate/sample fields differ. These ledger summaries do not prove that the underlying primitive producer states were identical.

`comparison.json` binds both row hashes, the C12 gzip hash, a 170,472,964-byte bounded C13 prefix hash, and copies/hashes of the C12 and C13 process identities. The C13 identity shows the native process was running when captured. The C13 ledger is append-only and remains unclosed here; this is not a final runtime, science, area-weighted, or budget result. C12’s closed run receipt is itself `INCOMPLETE` with return code 1.
