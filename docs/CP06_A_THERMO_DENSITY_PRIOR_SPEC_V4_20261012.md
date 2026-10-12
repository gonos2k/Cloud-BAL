# CP06-A thermodynamic density-prior experiment, revision 4

This revision freezes one internal numerical solver setting before the next
retained 13 UTC candidate run. The case, hash-bound inputs, thermodynamic prior,
trial masks, external acceptance thresholds, support windows, and increment
caps remain unchanged.

## Prior revisions and observed numerical issue

Revision 1 remains rejected at the unchanged saturation gate: a zero-liquid
cell cannot keep vapor fixed while its density-prior temperature moves below
saturation. Revision 2 added the frozen zero-reservoir saturation inequality;
the code path passed that thermo/Phi stage, but its retained runner stopped on
receipt-check defects before a force-prior trial was included. Revision 3
included the frozen 900-cell force-prior stage and up to 20 stored-state
halvings. It still rejected the retained candidate: the final shared-flux RMS
was `2.3471997393997733e-10`, above the unchanged external limit
`2.339591491450392e-10`. Its continuity-corrected input was
`2.3395234102527681e-10`, leaving only `6.8e-15` RMS margin for a float32
stored wind correction. Revision 1–3 documents and receipts remain unchanged.

## Internal solver headroom

Set the existing `balance%solver_residual_fraction` for this trial to
`1.0e-3`, instead of its default `2.0e-3`. This tightens the existing internal
normal-equation stopping criterion before the final stored candidate is
checked. It does not alter the force prior, analytic direction, backtracking,
external continuity acceptance (`0.002` of the original residual, including
the unchanged absolute floor), strict objective-decrease rule, absolute-force
rule, or hard wind and omega caps. The retained force stage may accept the
analytic stored trial directly or use up to 20 halvings; it must still pass
every current stored-state gate. A failed trial remains rejected atomically.

Keep the original 2026-08-16 13 UTC CP06-A input on the 235×283×22 grid and
all fixed supports: 162 material cells, 69 liquid-thermodynamic cells, 180
Phi cells, 500 wind controls, 980 continuity validation cells, and 900 force
cells. Keep density-prior background weight 0.5 and the 5 K and 0.005 kg/kg
thermodynamic bounds, 10 m/s wind cap, and 5 Pa/s omega cap.

## Validation and scope

Require one accepted joint thermo/Phi/force candidate, exact same-trial
condensate preservation, unchanged cloud/radar observation signal, final
composition-based continuity operator reconstruction and shared-flux receipt,
writer producer replay, and rejection without output for nonfinite ledger and
same-trial witness mutations. Run the separate over-cap trial and verify full
atomic rollback. Record the exact solver fraction and force backtracking count.

This is a numerical precision setting for the existing retrieval experiment,
not new scientific authority or a relaxed acceptance envelope. Do not change
supports, weights, external gates, observation treatment, caps, or source
claims. No native promotion or physical conservation claim follows from a
successful diagnostic trial.
