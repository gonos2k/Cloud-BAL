from pathlib import Path
import json,hashlib
s=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_two_hour_probe_20261103/analysis_scratch')
b=Path('/var/tmp/b1-two-hour-probe-20261103')
run=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_two_hour_probe_20261103/analysis_run1')
ind=json.loads((s/'independent_trace_review.json').read_text()); per={x['case']:x for x in ind['cases']}
counts={}
for arm in ['OLD','FIX']:
 groups={}
 for name,v in per[arm]['exact_zero_raw_events_by_point_and_hour'].items():
  point,hour=name.split('_'); groups[f'{point}_{hour}']={
   'exact_zero_PREVP_RAW_events':v['zero_raw_events'],
   'negative_PREVP_SAT_CAP_events':v['negative_sat_cap_events'],
   'negative_final_PROCESS_RATES_PREVP_events':v['negative_final_process_events'],
   'negative_SAT_CAP_itimestep_min':v['negative_satcap_first_step'],
   'negative_SAT_CAP_itimestep_max':v['negative_satcap_last_step'],
   'sum_final_PROCESS_PREVP_times_dtcld_over_event_records':v['sum_final_prevp_dtcld_over_events'],
   'sum_scope':'sum across recorded levels/corners/transactions; not a physical column or domain budget'}
 counts[arm]=groups
summ={arm:json.loads((run/arm/f'{arm.lower()}_summary.json').read_text()) for arm in ['OLD','FIX']}
result={
 'status':'INDEPENDENT_SCIENCE_REVIEW_COMPLETE_OBSERVATION_ONLY',
 'scope':'Independent bounded review of selected-cell KDM6 traces from the same-B1 OLD/FIX two-hour runs. This review did not change the model, parser, run, or raw payloads.',
 'provenance':{
  'same_B1_wrfinput_sha256':'9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5',
  'strict_history_and_trace_gates':{
   'OLD':{'path':str(b/'cases/OLD/full_prefix_gate_v1.json'),'sha256':'8c7341934910f908c64c83990504df9a2a82fdcc35a76a209f2db49f41dc6c86','status':'PASS_FULL_PREFIX','exe_sha256':'916bac01f950c4c900947a264767b573d0735413c0d2883ff4f13eead4729cc1','decompressed_trace_sha256':'ad62a98072b25cc2f6cadfaaf31e5111ab698985d446c69b398303bcfbe075a8','compressed_trace_sha256':'9bc68ad9da6c2324bc8674079f49f10584fa388f028d9ce8e980b5d387c5c773'},
   'FIX':{'path':str(b/'cases/FIX/full_prefix_gate_v1.json'),'sha256':'fad38282473f00fabe1ca5e4fe54ffba3b8939d04062ddc5edb36d262cea49a6','status':'PASS_FULL_PREFIX','exe_sha256':'149ce39b6b79a5c296aee96f6d6caa3b51e18e6b91ef1935718339d3b4fe658c','decompressed_trace_sha256':'0421252d30c2e7a755124f1835263e90b7fd9b4340dc5e73dabdfd00fd049c13','compressed_trace_sha256':'753c2168670baae19524b8632e33d91d76b86d949da84bc80ae179b6604d3c16'}},
  'instrumented_source_sha256':{'BASE_OLD':'b3a7f22c5929eab80784b2b2963e34798811b16c0f9a433601b16498f52aae02','FIX':'bd4e0a021f770daf0fbbdedfa3f07b964638edac5b3fb1b1f97dbe4826b72e90'},
  'candidate_patch_sha256':'94f109e624aa0b3b25689db20b1ac1acb4122920288d3765499147ed385fea3e',
  'analysis_summary_sha256':{'OLD':hashlib.sha256((run/'OLD/old_summary.json').read_bytes()).hexdigest(),'FIX':hashlib.sha256((run/'FIX/fix_summary.json').read_bytes()).hexdigest()},
  'trace_scope':{'native_cells':16,'levels_per_cell':39,'itimestep':[1,360],'time_step_seconds':20,'phase_update_rows_per_arm':224640,'transaction_key':'rank, call_id, itimestep, loop, j, i, k'}},
 'independent_method':{'script':str(s/'independent_trace_review.py'),'script_sha256':hashlib.sha256((s/'independent_trace_review.py').read_bytes()).hexdigest(),'result':str(s/'independent_trace_review.json'),'result_sha256':hashlib.sha256((s/'independent_trace_review.json').read_bytes()).hexdigest(),'method':'Custom gzip streaming/token reader, independent of maintained analyzer. Paired logged phases on the full transaction key; decoded signed int32 REAL32 and int64 REAL64 transfer words. Cross-checked zero-event counts against run1 summary CSVs.','duplicate_phase_keys':{'OLD':per['OLD']['duplicate_relevant_records'],'FIX':per['FIX']['duplicate_relevant_records']}},
 'observations':{
  'source_difference':{'BASE_OLD':'Instrumented source line 1849 has unconditional ELSE, followed at 1850 by MIN(prevp,satdt/2).','FIX':'Instrumented source line 1849 has ELSE IF (prevp.ne.0.), so exact zero bypasses that MIN.','bounded_read':'Observed OLD zero raw events with negative satdt become negative at SAT_CAP; FIX exact-zero events remain zero. This matches the source branch difference, without claiming a precipitation-score or full-budget effect.'},
  'exact_zero_events_by_point_and_hour':counts,
  'arm_totals':{'OLD':{'raw_zero':per['OLD']['selected_exact_zero_PREVP_RAW_count'],'negative_sat_cap':per['OLD']['selected_exact_zero_PREVP_RAW_cap_negative_count'],'negative_final_process':per['OLD']['selected_exact_zero_PREVP_RAW_process_negative_count'],'final_process_zero':per['OLD']['selected_exact_zero_PREVP_RAW_process_zero_count'],'negative_cap_itimestep_minmax':per['OLD']['exact_zero_raw_cap_negative_timestep_minmax']},'FIX':{'raw_zero':per['FIX']['selected_exact_zero_PREVP_RAW_count'],'negative_sat_cap':per['FIX']['selected_exact_zero_PREVP_RAW_cap_negative_count'],'negative_final_process':per['FIX']['selected_exact_zero_PREVP_RAW_process_negative_count'],'final_process_zero':per['FIX']['selected_exact_zero_PREVP_RAW_process_zero_count'],'negative_cap_itimestep_minmax':per['FIX']['exact_zero_raw_cap_negative_timestep_minmax']}},
  'number_moment_observations':{'OLD':'All 1,185 exact-zero PREVP_RAW rows also had zero formula PREVP, nrs=0, REAL64 n0r=0.','FIX':'Of 1,542 exact-zero PREVP_RAW rows, 1,531 had nrs=0 and n0r=0. Eleven had tiny positive nrs (1.0930e-42 to 4.3660e-35) and n0r (1.3389e-33 to 5.3483e-26), captured RH 0.8480 to 0.9116, fac_evap=1; their formula and raw PREVP words were signed zero.','limit':'The eleven rows do not establish why formula PREVP is zero. Formula operands are omitted from the trace; no initializer, underflow, or PSD mechanism is inferred.'},
  'local_q_T_equation_replay':{'equations':'q_post = q_pre + REAL32(work2*dtcld); T_post = T_pre - REAL32(REAL32(xlwork2/cpm)*dtcld).','OLD':{'matched_zero_raw_updates':per['OLD']['zero_PREVP_RAW_update_correspondence']['matched_pre_latent_post_process_count'],'max_q_REAL32_replay_residual':per['OLD']['zero_PREVP_RAW_update_correspondence']['max_abs_q_update_residual_after_real32_rounding'],'max_T_REAL32_replay_residual':per['OLD']['zero_PREVP_RAW_update_correspondence']['max_abs_T_update_residual_after_real32_rounding']},'FIX':{'matched_zero_raw_updates':per['FIX']['zero_PREVP_RAW_update_correspondence']['matched_pre_latent_post_process_count'],'max_q_REAL32_replay_residual':per['FIX']['zero_PREVP_RAW_update_correspondence']['max_abs_q_update_residual_after_real32_rounding'],'max_T_REAL32_replay_residual':per['FIX']['zero_PREVP_RAW_update_correspondence']['max_abs_T_update_residual_after_real32_rounding']},'interpretation':'All matched zero-raw event updates replay exactly at REAL32 precision. This checks local state arithmetic; it does not isolate process causality or establish a full budget.'},
  'qrs_zero_and_raw_prevp_negative_event_count':{'OLD':per['OLD']['selected_qrs_zero_and_PREVP_RAW_negative_count'],'FIX':per['FIX']['selected_qrs_zero_and_PREVP_RAW_negative_count']},
  'official_analyzer_crosscheck':{'OLD':{'transaction_count':summ['OLD']['transaction_count'],'max_abs_q_equation_residual':summ['OLD']['max_abs_q_equation_residual'],'max_abs_T_equation_residual':summ['OLD']['max_abs_t_equation_residual'],'max_abs_q_source_order_residual':summ['OLD']['max_abs_q_residual'],'max_abs_T_source_order_residual':summ['OLD']['max_abs_t_residual']},'FIX':{'transaction_count':summ['FIX']['transaction_count'],'max_abs_q_equation_residual':summ['FIX']['max_abs_q_equation_residual'],'max_abs_T_equation_residual':summ['FIX']['max_abs_t_equation_residual'],'max_abs_q_source_order_residual':summ['FIX']['max_abs_q_residual'],'max_abs_T_source_order_residual':summ['FIX']['max_abs_t_residual']}}},
 'limits':['Four post hoc points with four native corners each; no pooled performance inference.','Transaction sums cover levels/corners and are not mass-column, water, or energy budgets.','The logged PREVP_FORMULA omits terms needed to replay the complete expression.','No upstream QNRAIN initialization or general KDM6 policy is established by these runs.','No CSI change, score improvement, precipitation causality, candidate selection, or production approval is claimed.']}
out=s/'science_review.json'; out.write_text(json.dumps(result,indent=2)+'\n'); print(out,hashlib.sha256(out.read_bytes()).hexdigest())
