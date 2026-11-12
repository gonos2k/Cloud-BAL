# Frozen synthetic implementation validation

`run.py` copies the declared source set to a fresh directory outside the original
Cloud-BAL checkout. It builds the common kernel and both adapters with the pinned
Intel audit and optimized profiles. Each profile runs three Fortran programs,
10 new Python boundary test methods and the19 existing file-adapter methods.
The existing microphysics and joint proposal tests protect the old path.

The original and copied source hashes must match before and after execution.
The recipe itself is included. Logs are retained with SHA-256 in receipt.json.
Test registration is checked against the full original tree; the smaller frozen
copy is deliberately not presented as the complete project corpus.

The earlier development runs were not the final frozen validation basis. Their
logs remain outside the source checkout under the batch scratch directories.
The final logs and receipt are the publication evidence.

No real independent background passed this workflow in the current batch.
Synthetic metadata attestations are test fixtures, not observed PSD information.
No new WRF run, initial-condition adoption or independent-event skill was tested.
