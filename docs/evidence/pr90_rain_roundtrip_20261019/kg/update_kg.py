#!/usr/bin/env python3
"""Guarded selected-path Graphify/KG update for PR90 rain-roundtrip diagnostics.
External scratch utility; no apply/freeze is enabled until root supplies reviewed pins."""
from __future__ import annotations
import argparse, hashlib, importlib.metadata, importlib.util, json, os, re, shutil, stat, subprocess, sys, time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50')
MAINT=ROOT/'Cloud-BAL'
SOURCE=ROOT/'scratch/pr90_rain_roundtrip_20261019/Cloud-BAL'
OUT=MAINT/'scratch/pr90_rain_roundtrip_20261019'
BASE='3bc7bb8df6a100b60c6f8908ad93a7c3d981f360'
PRIOR=MAINT/'scratch/pr89_process_contract_20261019/kg_receipt.json'
PRIOR_SHA='80df43e8df44698c597119db5bb70466e7bc265ee77e2f76c0cfc5bcaa5589c3'
PRIOR_ALIAS=None
APPROVED_SELECTED_PATHS=frozenset(('docs/PR90_C5_HISTORY_20261019.md', 'docs/PR90_C7_HISTORY_20261019.md', 'docs/PR90_RAIN_ROUNDTRIP_20261019.md', 'docs/evidence/pr90_c5_history_20261019/history/paired_history.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/COUPLED_preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/COUPLED_run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/OFF_preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/OFF_run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/OFF_t8_failure_replay.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/archive_verification.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/build_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/failure_excerpt.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/manifest.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/overrides.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/coupled_generic_completed_state_audit.json.gz', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/independent_runtime_audit.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/independent_runtime_audit.py', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/off_generic_completed_state_audit.json.gz', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/runtime/source_inactive_ice_split.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/science/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/science/area_weighted_completed_prefix.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c6/sources.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/COUPLED/preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/COUPLED/run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/OFF/preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/OFF/run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/COUPLED/preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/COUPLED/run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/OFF/preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/OFF/run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/failure_classification.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/failure_classification.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/runtime/SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/runtime/coupled_prefix_and_t10_audit.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/runtime/off_prefix_and_t10_audit.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/runtime/verify_prefix_and_t10_tail.py', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/build_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/overrides.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/coupled_generic_completed_state_audit.json.gz', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/independent_runtime_audit.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/independent_runtime_audit.py', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/off_generic_completed_state_audit.json.gz', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/runtime/source_inactive_ice_split.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/area_weighted_180s.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/extract_psd_t8_event.py', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/history_180s.SHA256SUMS', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/history_180s.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/joint_absence/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/joint_absence/audit_joint_absence.py', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/joint_absence/result_180s.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/science/psd_t8_event.json', 'docs/evidence/pr90_rain_roundtrip_20261019/c7/sources.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/build_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/compiled_joint_transport.f90', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/compiled_rain_diagnostic.f90', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/compiled_rain_ng_consumer.f90', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/independent_review.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/independent_review.md', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/independent_review.py', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/manifest.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/preflight.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/replay.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/replay_scoped.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d1/run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/build_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/capture_t7_packet.py', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/producer_trace.raw.gz', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/run_receipt.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/science/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/science/area_weighted_prefix.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/t7_target_packet.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/t7_target_packet_seed.json', 'docs/evidence/pr90_rain_roundtrip_20261019/d2/warm_ledger.raw.gz', 'docs/evidence/pr90_rain_roundtrip_20261019/manifest.json', 'docs/evidence/pr90_rain_roundtrip_20261019/review/c7_final_psd_review.md', 'docs/evidence/pr90_rain_roundtrip_20261019/review/c7_joint_absence_review.md', 'docs/evidence/pr90_rain_roundtrip_20261019/review/c7_review_manifest.json', 'docs/evidence/pr90_rain_roundtrip_20261019/review/final_prepublication_review.md', 'docs/evidence/pr90_rain_roundtrip_20261019/review/focused_receipt_review.md', 'docs/evidence/pr90_rain_roundtrip_20261019/review/focused_tests.log', 'docs/evidence/pr90_rain_roundtrip_20261019/review/focused_tests.xml', 'docs/evidence/pr90_rain_roundtrip_20261019/review/focused_validation.json', 'docs/evidence/pr90_rain_roundtrip_20261019/review/science_scope_review.md', 'docs/evidence/pr90_rain_roundtrip_20261019/review/standalone_joint_transport.log', 'docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/README.md', 'docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/audit_joint_absence.py', 'docs/evidence/pr90_rain_roundtrip_20261019/science/joint_absence/result.json', 'src/common/cloud_bal_joint_transport.f90', 'tests/test_pr89_ice_consumer_contract.py', 'tests/test_pr89_paired_history.py', 'tests/test_pr90_cold_column_summary.py', 'tests/test_pr90_execution_layout.py', 'tests/test_pr90_joint_store_reason.py', 'tests/test_pr90_rain_failure_replay.py', 'tests/test_pr90_rain_final_psd.py', 'tests/test_pr90_rain_producer_trace.py', 'tests/test_pr90_rain_public_roundtrip.f90', 'tests/test_pr90_rain_public_roundtrip.py', 'tests/test_pr90_warm_rain_output.py', 'tools/pr86_time_response.py', 'tools/pr87_rain_public_store.f90', 'tools/pr89_paired_history.py', 'tools/pr90_cold_column_summary.py', 'tools/pr90_prepare_native_roundtrip.py', 'tools/pr90_rain_failure_replay.py', 'tools/pr90_rain_final_psd.py', 'tools/pr90_rain_producer_trace.py', 'tools/pr90_warm_rain_output.py'))
OLD_AUDIT=MAINT/'scratch/pr59_team_audit_20261006'
OLD_PUBLISH=MAINT/'scratch/pr59_publish_kg_20261002'
DELEGATED_UPDATER=OLD_PUBLISH/'update.py'
DELEGATED_UPDATER_SHA256='7c626b398f44a4013a607e2a5ae932528d2caaf41e37a479366aa80e0b146aa0'
DELEGATED_AUDITOR=OLD_AUDIT/'update_kg.py'
DELEGATED_AUDITOR_SHA256='bfe6242618e8ca1b60ab1304221d1fd215476d7f23281b69e48963611c0b76e1'
INTEGRATION_PATH='docs/evidence/pr90_rain_roundtrip_20261019/manifest.json'
VALIDATION_PATH='docs/evidence/pr90_rain_roundtrip_20261019/review/focused_validation.json'
VALIDATION_SHA256='44b67fec1c1570597582bf1d97fe301fcd901ae3ae0d6e20c3f61ab1157fa841'
VALIDATION_SCHEMA='pr90_focused_validation_v1'
VALIDATION_TEST_COUNT=95
INTEL_PROFILE_SHA256='5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4'
VALIDATION_SOURCE_PATHS=frozenset(('src/common/cloud_bal_joint_transport.f90', 'tests/test_pr89_ice_consumer_contract.py', 'tests/test_pr89_paired_history.py', 'tests/test_pr90_cold_column_summary.py', 'tests/test_pr90_execution_layout.py', 'tests/test_pr90_joint_store_reason.py', 'tests/test_pr90_rain_failure_replay.py', 'tests/test_pr90_rain_final_psd.py', 'tests/test_pr90_rain_producer_trace.py', 'tests/test_pr90_rain_public_roundtrip.f90', 'tests/test_pr90_rain_public_roundtrip.py', 'tests/test_pr90_warm_rain_output.py', 'tools/pr86_time_response.py', 'tools/pr87_rain_public_store.f90', 'tools/pr89_paired_history.py', 'tools/pr90_cold_column_summary.py', 'tools/pr90_prepare_native_roundtrip.py', 'tools/pr90_rain_failure_replay.py', 'tools/pr90_rain_final_psd.py', 'tools/pr90_rain_producer_trace.py', 'tools/pr90_warm_rain_output.py'))
INTEGRATION_SHA256='f4eabb1c3a4b7ee891de4efb0c81e3c83aee22a77b06ce7d77ce314ad3131488'
EXPECTED_COMMIT='60b02162e4f94a15db1b08cbe8a6ccd0ed9f0042'
EXPECTED_PR_URL='https://github.com/gonos2k/Cloud-BAL/pull/90'
INTEGRATION_SCHEMA='pr90_rain_roundtrip_integration_v1'
PRIOR_SNAPSHOT='2026-10-19-process-contract'
SNAPSHOT='2026-10-19-rain-roundtrip'
MAINTAINED_SOURCE_SHA256='0d11babbb4095a849093a512e499648d5dc51717e83710e1edf206041bb4346f'
ALLOWLIST_FROZEN=True
PR=EXPECTED_PR_URL
HELPER=Path(__file__).resolve()
GRAPHIFY_PY=Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/python3')
GRAPHIFY_CLI=Path('/home/korea_keun/.local/share/uv/tools/graphifyy/bin/graphify')

# Runtime pins remain fail-closed until root freezes both the final 180-second and
# 600-second outcomes, receipts, and executable identity. INCOMPLETE is
# allowed when the exact closed receipt documents it; graph update does not require COMPLETE.
RUNTIME_FREEZE_READY=True
EXPECTED_RUNTIMES={'180': {'status': 'COMPLETE', 'run_identity': 'PR87 selected-object native candidate', 'requested_duration_seconds': 180, 'timestep_seconds': 20, 'executed_executable_sha256': '5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572', 'arms': {'OFF': {'status': 'COMPLETE', 'returncode': 0, 'final_completed_step': 9, 'timestep_count': 9, 'receipt_path': 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/OFF/run_receipt.json', 'receipt_sha256': '3dc5773680fb0d92cbdf2aeb0a8ebaa1739e11c6366152add51e949c6f767ab1'}, 'COUPLED': {'status': 'COMPLETE', 'returncode': 0, 'final_completed_step': 9, 'timestep_count': 9, 'receipt_path': 'docs/evidence/pr90_rain_roundtrip_20261019/c7/180/COUPLED/run_receipt.json', 'receipt_sha256': '72fe00aebe9db05270c747b974218114d3f3f83d1d7c6a87d4032b6399c5a0e0'}}}, '600': {'status': 'INCOMPLETE', 'run_identity': 'PR87 selected-object native candidate', 'requested_duration_seconds': 600, 'timestep_seconds': 20, 'executed_executable_sha256': '5f5599e38759a9e2be27a9e7e0977370592c92cab328062d07eb359bddd19572', 'arms': {'OFF': {'status': 'INCOMPLETE', 'returncode': 1, 'final_completed_step': 9, 'timestep_count': 9, 'receipt_path': 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/OFF/run_receipt.json', 'receipt_sha256': 'd1802d60e5263ff5f2c02aee7b38e35bce274eb93e48bf3e40da75d113dd951d'}, 'COUPLED': {'status': 'INCOMPLETE', 'returncode': 1, 'final_completed_step': 9, 'timestep_count': 9, 'receipt_path': 'docs/evidence/pr90_rain_roundtrip_20261019/c7/600/COUPLED/run_receipt.json', 'receipt_sha256': '4142a65a5a66e4b9b262c1a239218d60c21cb672a89b737d9f605fc597a66d53'}}}}

def sha_bytes(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def sha(p:Path)->str:return sha_bytes(p.read_bytes())
def git(*args,cwd=SOURCE):return subprocess.check_output(['git',*args],cwd=cwd,text=True).rstrip()
def fail(msg):raise RuntimeError('guard failed: '+msg)
def regular_file(path:Path):
    if not stat.S_ISREG(path.lstat().st_mode):fail(f'non-regular selected artifact: {path}')
def reject_symlink_ancestors(path:Path):
    for part in (path,*path.parents):
        if part.is_symlink():fail(f'symlinked output component: {part}')

def guard_destination(path:Path,root:Path=ROOT):
    reject_symlink_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'destination escapes expected root {root}: {path}')
    if path.exists():regular_file(path)

def guard_directory(path:Path,root:Path=ROOT):
    reject_symlink_ancestors(path)
    if not path.resolve().is_relative_to(root.resolve()):
        fail(f'directory escapes expected root {root}: {path}')
    if not path.is_dir():fail(f'expected directory: {path}')

def delegated_importer_bindings()->dict:
    bindings={}
    for label,path,expected in (
        ('updater',DELEGATED_UPDATER,DELEGATED_UPDATER_SHA256),
        ('auditor',DELEGATED_AUDITOR,DELEGATED_AUDITOR_SHA256),
    ):
        guard_destination(path,MAINT);regular_file(path)
        actual=sha(path)
        if actual!=expected:fail(f'delegated {label} source SHA drift: {path}')
        bindings[label]={'path':str(path),'sha256':actual}
    return bindings

def validate_closed_runtime(runtime:dict,executable:str)->dict:
    if not RUNTIME_FREEZE_READY:
        fail('freeze exact closed 180-second and 600-second runtime outcomes, executable, and receipt hashes first')
    if 'TODO_' in json.dumps(EXPECTED_RUNTIMES,sort_keys=True):
        fail('closed runtime literals still contain TODO values')
    windows=runtime.get('windows')
    if not isinstance(windows,dict) or set(windows)!=set(EXPECTED_RUNTIMES):
        fail('manifest must include exactly the frozen 180-second and 600-second runtime windows')
    closed_windows={}
    window_statuses=[]
    for duration_key,expected in EXPECTED_RUNTIMES.items():
        window=windows[duration_key]
        duration=expected.get('requested_duration_seconds')
        timestep=expected.get('timestep_seconds')
        if duration!=int(duration_key) or timestep!=20 or duration%timestep:
            fail(f'frozen {duration_key}-second window must bind its duration and 20-second timestep')
        if expected.get('executed_executable_sha256')!=executable:
            fail(f'frozen {duration_key}-second executable differs from the bound native build')
        for key in ('run_identity','requested_duration_seconds','timestep_seconds','status'):
            if window.get(key)!=expected.get(key):
                fail(f'{duration_key}-second manifest {key} differs from frozen closed receipt')
        expected_arms=expected.get('arms')
        arms=window.get('arms')
        if not isinstance(expected_arms,dict) or set(expected_arms)!={'OFF','COUPLED'} or \
                not isinstance(arms,dict) or set(arms)!={'OFF','COUPLED'}:
            fail(f'frozen {duration_key}-second window must include exact OFF and COUPLED outcomes')
        statuses={}
        steps=duration//timestep
        for arm,expected_row in expected_arms.items():
            row=arms[arm]
            if row.get('status')!=expected_row['status']:
                fail(f'{duration_key}-second {arm} manifest status differs from frozen closed receipt')
            if type(row.get('returncode')) is not int or row['returncode']!=expected_row['returncode']:
                fail(f'{duration_key}-second {arm} manifest returncode differs from frozen closed receipt')
            if row.get('final_completed_step')!=expected_row['final_completed_step']:
                fail(f'{duration_key}-second {arm} manifest final step differs from frozen closed receipt')
            if row.get('final_completed_step') is not None and type(row.get('final_completed_step')) is not int:
                fail(f'{duration_key}-second {arm} final step must be an integer or null')
            if row.get('timestep_count')!=expected_row['timestep_count']:
                fail(f'{duration_key}-second {arm} manifest timestep count differs from frozen closed receipt')
            if type(row.get('timestep_count')) is not int:
                fail(f'{duration_key}-second {arm} timestep count must be an integer')
            receipt_ref=row.get('receipt')
            if not isinstance(receipt_ref,dict) or receipt_ref.get('path')!=expected_row['receipt_path']:
                fail(f'{duration_key}-second {arm} receipt path differs from frozen closed receipt')
            if receipt_ref.get('sha256')!=expected_row['receipt_sha256']:
                fail(f'{duration_key}-second {arm} receipt SHA differs from frozen closed receipt')
            status=expected_row['status']
            if status not in ('COMPLETE','INCOMPLETE'):
                fail(f'{duration_key}-second {arm} frozen status must be COMPLETE or INCOMPLETE')
            if type(expected_row['returncode']) is not int:
                fail(f'{duration_key}-second {arm} frozen returncode must be an integer')
            step=expected_row['final_completed_step']
            if step is not None and (type(step) is not int or not 0<=step<=steps):
                fail(f'{duration_key}-second {arm} final step must be null or within its window')
            if type(expected_row['timestep_count']) is not int or not 0<=expected_row['timestep_count']<=steps:
                fail(f'{duration_key}-second {arm} timestep count must be within its window')
            statuses[arm]=status
        aggregate='COMPLETE' if set(statuses.values())=={'COMPLETE'} else 'INCOMPLETE'
        if expected.get('status')!=aggregate or window.get('status')!=aggregate:
            fail(f'{duration_key}-second aggregate status must match its two frozen arm outcomes')
        window_statuses.append(aggregate)
        closed_windows[duration_key]={
            'requested_duration_seconds':duration,'timestep_seconds':timestep,
            'expected_timesteps':steps,'run_identity':expected['run_identity'],
            'status':aggregate,'executed_executable_sha256':executable,
            'arms':{arm:dict(expected_arms[arm]) for arm in ('OFF','COUPLED')}}
    aggregate='COMPLETE' if set(window_statuses)=={'COMPLETE'} else 'INCOMPLETE'
    if runtime.get('status')!=aggregate:
        fail('overall runtime status must match both frozen duration windows')
    return {'status':aggregate,'windows':closed_windows}

def expected_model_timestamps(duration_seconds:int,timestep_seconds:int=20)->list[str]:
    start=datetime(2026,8,16,13)
    return [(start+timedelta(seconds=timestep_seconds*step)).strftime('%Y-%m-%d_%H:%M:%S')
            for step in range(1,duration_seconds//timestep_seconds+1)]

def validate_runtime_receipt(arm:str,receipt:dict,expected:dict,window:dict,executable:str)->None:
    for key in ('status','returncode','timestep_count','final_completed_step'):
        if receipt.get(key)!=expected[key]:fail(f'{arm} receipt {key} differs from frozen final outcome')
    if receipt.get('arm')!=arm:fail(f'{arm} receipt arm identity mismatch')
    duration=window['requested_duration_seconds']
    timestep=window['timestep_seconds']
    steps=window['expected_timesteps']
    if receipt.get('run_identity')!=window['run_identity']:
        fail(f'{arm} receipt run identity differs from frozen final outcome')
    if receipt.get('executed_executable_sha256')!=executable or \
            receipt.get('expected_executed_executable_sha256')!=executable:
        fail(f'{arm} receipt executable differs from frozen candidate build')
    if receipt.get('candidate_build_unchanged') is not True:
        fail(f'{arm} receipt does not certify an unchanged candidate build')
    if receipt.get('source_receipt_unchanged') not in (None,True):
        fail(f'{arm} receipt reports a changed source receipt')
    source_receipt_sha=receipt.get('source_receipt_sha256')
    if not isinstance(source_receipt_sha,str) or not re.fullmatch(r'[0-9a-f]{64}',source_receipt_sha):
        fail(f'{arm} receipt does not bind its input source receipt SHA')
    if receipt.get('changed_staged_inputs') or receipt.get('changed_original_inputs'):
        fail(f'{arm} receipt records changed staged/original inputs')
    expected_times=expected_model_timestamps(duration,timestep)
    if receipt.get('expected_model_timestamps')!=expected_times:
        fail(f'{arm} receipt does not bind the complete {duration}-second timestamp schedule')
    actual=receipt.get('model_timestamps')
    if not isinstance(actual,list) or len(actual)!=expected['timestep_count']:
        fail(f'{arm} receipt timestamp count differs from frozen final outcome')
    actual_times=[row.get('timestamp') for row in actual if isinstance(row,dict)]
    if len(actual_times)!=len(actual) or any(value not in expected_times for value in actual_times):
        fail(f'{arm} receipt contains timestamps outside the {duration}-second schedule')
    actual_positions=[expected_times.index(value) for value in actual_times]
    if actual_positions!=sorted(set(actual_positions)):
        fail(f'{arm} receipt timestamps are duplicated or out of schedule order')
    if actual_times!=expected_times[:expected['timestep_count']]:
        fail(f'{arm} receipt timestamps are not the completed schedule prefix')
    completed=expected['final_completed_step']
    count=expected['timestep_count']
    if (count==0 and completed not in (None,0)) or (count>0 and completed!=count):
        fail(f'{arm} receipt final completed step does not match its timestep count')
    if expected['status']=='COMPLETE':
        if receipt['returncode']!=0 or expected['timestep_count']!=steps or expected['final_completed_step']!=steps:
            fail(f'{arm} COMPLETE status requires rc=0 and {steps} completed timesteps')
        if actual_times!=expected_times:fail(f'{arm} COMPLETE receipt does not contain all {steps} timestamps')
    elif receipt.get('status')!='INCOMPLETE':
        fail(f'{arm} closed unsuccessful run must remain explicitly INCOMPLETE')

def copy_checked(source:Path,target:Path):
    guard_destination(source)
    guard_destination(target)
    source_hash=sha(source)
    shutil.copy2(source,target)
    regular_file(target)
    if sha(source)!=source_hash or sha(target)!=source_hash:
        fail(f'copy verification failed: {source} -> {target}')

def restore_automatic_snapshots(snapshots):
    errors=[]
    for directory,members in snapshots.items():
        previous=Path(directory)
        try:guard_directory(previous)
        except BaseException as error:
            errors.append(f'{previous}: {error}')
            continue
        for name,record in members.items():
            try:
                backup=Path(record['backup'])
                if sha(backup)!=record['sha256']:fail('prior automatic snapshot backup drift')
                copy_checked(backup,previous/name)
                if sha(previous/name)!=record['sha256']:fail('prior snapshot content changed')
            except BaseException as error:
                errors.append(f'{previous/name}: {error}')
        # Unknown concurrent members are preserved; they require explicit review.
        try:
            if {p.name for p in previous.iterdir()}!=set(members):
                fail('prior snapshot membership changed; unknown files preserved')
        except BaseException as error:
            errors.append(f'{previous}: {error}')
    if errors:raise RuntimeError('automatic snapshot restore errors: '+'; '.join(errors))


def snapshot_path(path:Path,root:Path)->dict:
    relative=path.relative_to(root).as_posix()
    info=path.lstat()
    if stat.S_ISLNK(info.st_mode):
        return {'kind':'symlink','target':os.readlink(path)}
    if not stat.S_ISREG(info.st_mode):
        fail(f'non-regular active maintained path: {path}')
    return {'kind':'file','sha256':sha(path)}

def maintained_source_snapshot()->dict:
    """Hash active source/docs/config and tracked root files without traversing scratch trees."""
    allowed_wiki={"wiki/graph-report.md","wiki/graph-report-klaps50.md","wiki/graph-report-cloud-bal.md","wiki/index.md","wiki/log.md"}
    result={}
    for root in (ROOT,MAINT):
        root_git_dir=Path(git('rev-parse','--show-toplevel',cwd=root)).resolve()
        if not root.resolve().is_relative_to(root_git_dir):fail(f'maintained path escapes its Git root: {root}')
        for dirname in ('src','tests','docs','config'):
            base=root/dirname
            if not base.exists() and not base.is_symlink():continue
            if base.is_symlink():
                result[f'{root.name}/{dirname}']=snapshot_path(base,root)
                continue
            for current,dirs,files in os.walk(base,followlinks=False):
                current_path=Path(current)
                for name in list(dirs):
                    child=current_path/name
                    if name in {'scratch','worktrees','.git','graphify-out'}:
                        dirs.remove(name)
                        continue
                    if child.is_symlink():
                        result[f'{root.name}/{child.relative_to(root).as_posix()}']=snapshot_path(child,root)
                        dirs.remove(name)
                for name in files:
                    child=current_path/name
                    rel=child.relative_to(root).as_posix()
                    if root==ROOT and rel in allowed_wiki:continue
                    if child.is_symlink() or child.is_file():
                        result[f'{root.name}/{rel}']=snapshot_path(child,root)
        root_prefix=root.resolve().relative_to(root_git_dir).as_posix()
        # Include immediate tracked root files only; never recurse into scratch/worktrees.
        for child in root.iterdir():
            if not (child.is_file() or child.is_symlink()):continue
            rel=child.relative_to(root).as_posix()
            tracked_path=f'{root_prefix}/{rel}' if root_prefix!='.' else rel
            tracked=subprocess.run(['git','ls-files','--cached','--error-unmatch','--',tracked_path],cwd=root_git_dir,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
            if tracked.returncode==0:
                result[f'{root.name}/{rel}']=snapshot_path(child,root)
    for path in sorted((p for p in MAINT.glob('wiki/*') if p.is_file() or p.is_symlink())):
        rel=path.relative_to(MAINT).as_posix()
        if rel in allowed_wiki:continue
        result[f'Cloud-BAL/{rel}']=snapshot_path(path,MAINT)
    return result

def show(commit,path):return subprocess.check_output(['git','show',f'{commit}:{path}'],cwd=SOURCE)

def make_plan(commit:str):
    os.environ['TZ']='Asia/Seoul'; time.tzset()
    if date.today().isoformat()!='2026-10-19':fail('dated snapshot day differs from declared session day')
    if not ALLOWLIST_FROZEN or 'TODO_' in EXPECTED_COMMIT or 'TODO_' in EXPECTED_PR_URL:
        fail('freeze the reviewed literal allowlist, source commit, and actual PR URL before check-only/apply')
    if not re.fullmatch(r'https://github\.com/gonos2k/Cloud-BAL/pull/[1-9][0-9]*',EXPECTED_PR_URL):fail('frozen actual PR URL format mismatch')
    if commit!=EXPECTED_COMMIT:fail('requested commit differs from the reviewed frozen commit literal')
    if importlib.metadata.version('graphifyy')!='0.9.53':fail('Graphify package must be exactly 0.9.53')
    if Path(sys.executable).resolve()!=GRAPHIFY_PY.resolve():fail('run through pinned Graphify Python')
    if Path(shutil.which('graphify') or '').resolve()!=GRAPHIFY_CLI.resolve():fail('pinned Graphify CLI must be first on PATH')
    if git('rev-parse','HEAD')!=commit:fail('candidate HEAD differs from requested frozen SHA')
    if git('status','--porcelain'):fail('candidate source worktree is not clean')
    subprocess.run(['git','merge-base','--is-ancestor',BASE,commit],cwd=SOURCE,check=True)
    changed=git('diff','--name-status','--find-renames',BASE,commit).splitlines(); items=[]
    for row in changed:
        fields=row.split('\t')
        if len(fields)!=2 or fields[0] not in ('A','M'):fail(f'unsupported selected path change: {row}')
        status,rel=fields
        if rel not in APPROVED_SELECTED_PATHS:fail(f'unreviewed path cannot enter selected extraction: {rel}')
        candidate=SOURCE/rel; reject_symlink_ancestors(candidate)
        if not candidate.resolve().is_relative_to(SOURCE.resolve()):fail(f'selected candidate escapes source root: {candidate}')
        regular_file(candidate)
        maintained=MAINT/rel; guard_destination(maintained,MAINT)
        from graphify.extract import _get_extractor
        oldbytes=subprocess.run(['git','show',f'{BASE}:{rel}'],cwd=SOURCE,capture_output=True,check=False)
        items.append({'path':rel,'change':status,'base_sha256':sha_bytes(oldbytes.stdout) if oldbytes.returncode==0 else None,
          'candidate_sha256':sha(candidate),'maintained_before_sha256':sha(maintained) if maintained.is_file() else None,
          'graphify_extraction':'AST_OR_MARKDOWN_HEADING' if _get_extractor(candidate) is not None else 'NON_EXTRACTABLE_HASH_ONLY'})
    if not items or {x['path'] for x in items}!=set(APPROVED_SELECTED_PATHS):fail('frozen selected paths must exactly equal the complete base-to-commit diff')
    guard_destination(PRIOR)
    if sha(PRIOR)!=PRIOR_SHA:fail('preceding PR89 receipt hash drift')
    prior=json.loads(PRIOR.read_text())
    if prior.get('frozen_source_commit')!='da48cca65c57aeaad9daf717abe0a0d6b6df9e25':fail('preceding PR89 source identity mismatch')
    if prior.get('graphify_version')!='graphify 0.9.53':fail('preceding receipt Graphify version mismatch')
    current=maintained_source_snapshot()
    current_digest=sha_bytes(json.dumps(current,sort_keys=True,separators=(',',':')).encode())
    expected_inventory=prior.get('maintained_source_snapshot',{})
    if len(current)!=627 or expected_inventory.get('entry_count')!=627:fail('maintained source inventory must remain 627 entries')
    if current_digest!=MAINTAINED_SOURCE_SHA256:fail('maintained source inventory differs from pinned 627-entry digest')
    if current_digest!=expected_inventory.get('before_sha256'):fail('maintained source inventory differs from preceding receipt')
    expected_graphs={}
    for label in ('KLAPS50','Cloud-BAL'):
        record=prior.get('corpora',{}).get(label,{})
        if any(record.get(k)!=v for k,v in {'snapshot':'2026-10-19T06:43:11+00:00'}.items()):fail(f'{label} preceding graph snapshot identity mismatch')
        directory=ROOT if label=='KLAPS50' else MAINT
        live=directory/'graphify-out/graph.json'; guard_destination(live,directory)
        if sha(live)!=record.get('sha256'):fail(f'{label} live graph differs from latest PR89 baseline')
        for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
            artifact=directory/'graphify-out'/PRIOR_SNAPSHOT/name; guard_destination(artifact,directory)
            snapshot_record=prior.get('dated_snapshots',{}).get(label,{}).get(name,{})
            if not snapshot_record.get('after_sha256') or sha(artifact)!=snapshot_record['after_sha256']:
                fail(f'{label} latest dated PR89 snapshot drift: {name}')
            live_artifact=directory/'graphify-out'/name; guard_destination(live_artifact,directory)
            if sha(live_artifact)!=snapshot_record['after_sha256']:fail(f'{label} live derived graph artifact drift: {name}')
        next_snapshot=directory/'graphify-out'/SNAPSHOT; reject_symlink_ancestors(next_snapshot)
        if next_snapshot.exists():fail(f'{label} new dated snapshot already exists')
        expected_graphs[label]=record
    for rel,digest in prior.get('wiki_sha256',{}).items():
        path=ROOT/rel; guard_destination(path)
        if sha(path)!=digest:fail(f'wiki differs from latest PR89 receipt: {rel}')
    prior['corpora']=expected_graphs
    immutable={PRIOR:PRIOR_SHA,HELPER:sha(HELPER)}
    for label,files in prior.get('dated_snapshots',{}).items():
        for name,record in files.items():
            path=Path(record['path']); guard_destination(path)
            if sha(path)!=record['after_sha256']:fail(f'previous dated snapshot drift: {label}/{name}')
            immutable[path]=record['after_sha256']
    for path,digest in prior.get('prior_immutable_receipts',{}).items():
        p=Path(path); guard_destination(p,Path('/var/tmp') if p.is_relative_to(Path('/var/tmp')) else ROOT)
        if sha(p)!=digest:fail(f'previous immutable evidence drift: {path}')
        immutable[p]=digest
    if len(prior.get('prior_immutable_receipts',{}))!=181:fail('preceding PR89 receipt chain pin count mismatch')
    prior['_maintained_snapshot_digest']=current_digest
    delegated=delegated_importer_bindings()
    return items,prior,immutable,delegated

INHERITED_ACCEPTANCE_GATES=[
    "Whole host/thread FP policy beyond the selected single-thread cold start",
    "Joint Q/N/B validity during subsequent evolution beyond the declared latest validated window",
    "PBL DEL versus native dry-carrier global budget connection",
    "Physical justification and broader validation of conditional freezing and transient QG/BG admission",
    "Water and energy closure",
    "Physical small-ice inactive-to-active transitions and native count reconstruction",
]
OPEN_SAME_CANDIDATE_INTEGRATION_CONDITIONS=[
    "Independently justify observation/background covariance and validate observation fit",
    "Same-carrier dry-mass, water, and energy closure",
    "Spatial mass-wind compatibility at cells and shared faces after native initialization",
    "Physical compatibility after WPS/metgrid/real handoff",
    "Fixed-setting 10/30/60-minute response and independent observation signal preservation",
]

def validation_summary(document:dict,items:list[dict],commit:str)->str:
    if document.get('schema')!=VALIDATION_SCHEMA:fail('focused validation schema mismatch')
    if document.get('status')!='PASS':fail('focused validation receipt must record PASS')
    if type(document.get('test_count')) is not int or document['test_count']!=VALIDATION_TEST_COUNT:
        fail(f'focused validation must record exactly {VALIDATION_TEST_COUNT} passing tests')
    if document.get('compiler_profile')!='tests/intel_toolchain.sh':fail('focused validation must bind the pinned Intel profile')
    if document.get('compiler_profile_sha256')!=INTEL_PROFILE_SHA256:fail('pinned Intel profile hash mismatch')
    pins=document.get('source_hashes')
    if not isinstance(pins,dict) or set(pins)!=VALIDATION_SOURCE_PATHS:
        fail('focused validation source pin set mismatch')
    selected={item['path'] for item in items}
    for relative,digest in pins.items():
        if relative not in selected:fail(f'validation source is not selected in frozen diff: {relative}')
        path=SOURCE/relative; reject_symlink_ancestors(path); regular_file(path)
        if sha(path)!=digest:fail(f'focused validation source hash drift: {relative}')
        if sha_bytes(subprocess.check_output(['git','show',f'{commit}:{relative}'],cwd=SOURCE))!=digest:
            fail(f'focused validation source does not match frozen commit: {relative}')
    if document.get('physical_approval') is not False:fail('focused tests must not claim physical approval')
    standalone=document.get('standalone_intel')
    if not isinstance(standalone,dict) or standalone.get('source')!='tests/test_joint_qnb_transport.f90':
        fail('missing original standalone joint transport validation')
    if standalone.get('O0')!='PASS' or standalone.get('O2')!='PASS':
        fail('standalone joint transport must pass pinned Intel O0/O2')
    log_relative=standalone.get('log_path','')
    if not isinstance(log_relative,str) or Path(log_relative).is_absolute() or '..' in Path(log_relative).parts:
        fail('invalid standalone validation log path')
    if log_relative not in selected:fail('standalone log must be selected')
    log=SOURCE/log_relative; reject_symlink_ancestors(log); regular_file(log)
    if sha(log)!=standalone.get('log_sha256') or sha_bytes(show(commit,log_relative))!=sha(log):
        fail('standalone validation log hash drift')
    profile=SOURCE/'tests/intel_toolchain.sh'
    if sha(profile)!=INTEL_PROFILE_SHA256:fail('current pinned Intel profile hash mismatch')
    return f"{document['test_count']} focused Python/source-form tests and original joint transport Intel O0/O2 PASS; bounded diagnostics only."


def load_validation_receipt(argument:str|None,items:list[dict],commit:str):
    relative=Path(argument or VALIDATION_PATH)
    if relative.is_absolute() or '..' in relative.parts:fail('validation path must remain inside candidate source root')
    rel=relative.as_posix(); source=SOURCE/relative
    if rel not in {x['path'] for x in items}:fail('focused validation receipt must be selected in frozen source diff')
    regular_file(source); digest=sha(source)
    if digest!=VALIDATION_SHA256:fail('focused Intel validation receipt SHA differs from frozen literal')
    if sha_bytes(subprocess.check_output(['git','show',f'{commit}:{rel}'],cwd=SOURCE))!=digest:fail('validation receipt differs from frozen commit')
    document=json.loads(source.read_text(encoding='utf-8'))
    summary=validation_summary(document,items,commit)
    return {'path':rel,'sha256':digest,'source_commit':commit,'summary':summary,'document':document}


def load_integration_receipt(items:list[dict],commit:str)->dict:
    source=SOURCE/INTEGRATION_PATH
    if INTEGRATION_PATH not in {x['path'] for x in items}:fail('integration manifest must be in frozen selected diff')
    regular_file(source); digest=sha(source)
    if digest!=INTEGRATION_SHA256:fail('integration manifest SHA differs from frozen literal')
    if sha_bytes(subprocess.check_output(['git','show',f'{commit}:{INTEGRATION_PATH}'],cwd=SOURCE))!=digest:fail('manifest differs from frozen commit')
    document=json.loads(source.read_text(encoding='utf-8'))
    if document.get('schema')!=INTEGRATION_SCHEMA:fail('PR90 integration manifest schema mismatch')
    if document.get('base_commit')!=BASE:fail('integration manifest base commit mismatch')
    embedded_commit=document.get('source_commit',document.get('frozen_source_commit'))
    if embedded_commit is not None and embedded_commit!=commit:fail('integration manifest source commit mismatch')
    if document.get('physical_approval')!='FAIL_OPEN':fail('integration physical approval must remain FAIL_OPEN')
    validation=document.get('validation')
    if not isinstance(validation,dict) or validation.get('status')!='PASS' or validation.get('sha256')!=VALIDATION_SHA256:
        fail('manifest must bind the passing focused validation receipt SHA')
    def bound_json(record,label):
        if not isinstance(record,dict):fail(f'missing bound {label} artifact')
        relative=record.get('path','')
        if not isinstance(relative,str) or Path(relative).is_absolute() or '..' in Path(relative).parts:
            fail(f'invalid bound {label} path')
        if relative not in {item['path'] for item in items}:fail(f'unselected bound {label} path')
        path=SOURCE/relative; reject_symlink_ancestors(path); regular_file(path)
        digest=sha(path)
        if digest!=record.get('sha256') or sha_bytes(show(commit,relative))!=digest:
            fail(f'bound {label} hash drift')
        return json.loads(path.read_text())
    build=bound_json(document.get('native_build'),'native build')
    if build.get('status')!='PASS_OVERLAY_BUILD' or build.get('full_clean_build') is not False:
        fail('native build must remain a passing partial-host overlay')
    executable=build.get('executable_sha256')
    if not isinstance(executable,str) or not re.fullmatch(r'[0-9a-f]{64}',executable):
        fail('invalid bound executable hash')
    runtime=document.get('latest_actual_host')
    if not isinstance(runtime,dict):
        fail('manifest must record explicit native host runtime windows')
    closed_runtime=validate_closed_runtime(runtime,executable)
    windows=runtime['windows']
    for duration_key in EXPECTED_RUNTIMES:
        runtime_window=windows[duration_key]
        arms=runtime_window['arms']
        closed_window=closed_runtime['windows'][duration_key]
        for arm,row in arms.items():
            if not isinstance(row,dict) or not isinstance(row.get('status'),str) or not row['status'].strip():
                fail(f'invalid native status for {duration_key}-second {arm}')
            if type(row.get('returncode')) is not int or (row.get('final_completed_step') is not None and
                                                          type(row.get('final_completed_step')) is not int):
                fail(f'invalid native returncode/completed step for {duration_key}-second {arm}')
            if row['final_completed_step'] is not None and row['final_completed_step']<0:
                fail(f'negative completed step for {duration_key}-second {arm}')
            receipt=bound_json(row.get('receipt'),f'{duration_key}-second {arm} native receipt')
            for key in ('status','returncode','final_completed_step'):
                if receipt.get(key)!=row[key]:fail(f'{duration_key}-second {arm} native receipt {key} mismatch')
            if receipt.get('arm')!=arm or receipt.get('executed_executable_sha256')!=executable:
                fail(f'{duration_key}-second native arm/executable mismatch')
            if receipt.get('candidate_build_unchanged') is not True:
                fail(f'{duration_key}-second {arm} candidate build changed')
            if receipt.get('changed_staged_inputs') or receipt.get('changed_original_inputs'):
                fail(f'{duration_key}-second {arm} native input integrity failed')
            validate_runtime_receipt(arm,receipt,closed_window['arms'][arm],closed_window,executable)
    gates=document.get('candidate_scientific_gates')
    if not isinstance(gates,dict) or not gates:fail('manifest must retain explicit candidate scientific gates')
    if any(not isinstance(value,str) or not value.strip() for value in gates.values()):
        fail('candidate scientific gate statuses must be nonempty strings')
    return {'path':INTEGRATION_PATH,'sha256':digest,'source_commit':commit,
            'document':document,'closed_runtime':closed_runtime}

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--commit',required=True,help='exact clean frozen source commit SHA')
    ap.add_argument('--pr-url',default=None,help='frozen actual PR URL; required for every mode')
    ap.add_argument('--validation-receipt',default=VALIDATION_PATH,help='frozen changed Intel validation receipt path')
    mode=ap.add_mutually_exclusive_group(required=True)
    mode.add_argument('--check-only',action='store_true',help='read-only guard/preflight; never updates graphs/wiki')
    mode.add_argument('--apply',action='store_true',help='perform Graphify update and derived wiki sync')
    args=ap.parse_args()
    global PR
    PR=args.pr_url or PR
    if args.pr_url and args.pr_url!=EXPECTED_PR_URL:
        fail('--pr-url differs from frozen actual PR URL')
    if not args.pr_url or args.pr_url!=EXPECTED_PR_URL:fail('check-only and apply require the frozen actual PR URL via --pr-url')
    items,prior,immutable,delegated_pins=make_plan(args.commit)
    maintained_snapshot_verified=False
    maintained_before=maintained_source_snapshot()
    maintained_before_digest=sha_bytes(json.dumps(maintained_before,sort_keys=True,separators=(',',':')).encode())
    previous_source_snapshot=prior.get('maintained_source_snapshot',{})
    if len(maintained_before)!=627 or previous_source_snapshot.get('entry_count')!=627:
        fail('maintained source inventory must remain at the preceding PR89-bound 627 entries')
    if maintained_before_digest!=MAINTAINED_SOURCE_SHA256:
        fail('maintained source inventory differs from pinned 627-entry digest')
    if maintained_before_digest!=previous_source_snapshot.get('before_sha256'):
        fail('maintained source inventory differs from the exact preceding PR89-bound snapshot')
    validation=load_validation_receipt(args.validation_receipt,items,args.commit)
    integration=load_integration_receipt(items,args.commit)
    native_binding=integration
    pending_candidate_gates=integration['document'].get('candidate_scientific_gates',{'cold_summary':'NOT_EVALUATED'})
    if args.check_only:
        print(json.dumps({'ready':True,'mode':'CHECK_ONLY_NO_WRITES','source':str(SOURCE),'commit':args.commit,'base':BASE,
          'selected_paths':items,'non_extractable_paths':[x['path'] for x in items if x['graphify_extraction']=='NON_EXTRACTABLE_HASH_ONLY'],'previous_receipt_sha256':PRIOR_SHA,
          'baseline_graphs':{k:{x:prior['corpora'][k][x] for x in ('snapshot','nodes','edges','communities','sha256')} for k in ('KLAPS50','Cloud-BAL')},
          'validation_receipt':validation,'native_receipt_binding':native_binding,'closed_runtime':native_binding['closed_runtime'],
          'delegated_importer_pins':delegated_pins,'candidate_scientific_gates':pending_candidate_gates,
          'maintained_source_snapshot':{'entry_count':len(maintained_before),'symlink_entries':sum(v.get('kind')=='symlink' for v in maintained_before.values()),'before_sha256':maintained_before_digest,'sha256':maintained_before_digest,'verified_pre_post_equal':False},'new_output_path':str(OUT),'output_exists':OUT.exists()},indent=2));return
    # This output directory may contain only this external helper before the run.
    reject_symlink_ancestors(OUT)
    if OUT.exists() and set(p.name for p in OUT.iterdir())!={HELPER.name}:
        fail('new PR90 rain-roundtrip output directory is not fresh; refuses overwrite')
    protected={}
    for rel in ('wiki/hot.md','wiki/overview.md'):
        p=ROOT/rel
        guard_destination(p)
        protected[rel]=sha(p)
    protected_dirs=('wiki/.schema','wiki/.schema-proposals','wiki/.research-queue','wiki/entities','wiki/concepts','wiki/sources','wiki/decisions',
      'wiki/heuristics','wiki/experiences','wiki/procedures','wiki/queries')
    for rel in protected_dirs:
        p=ROOT/rel
        if p.exists():
            guard_directory(p)
            files=sorted(x for x in p.rglob('*') if x.is_file())
            for f in files:guard_destination(f)
            entries=[(f.relative_to(ROOT).as_posix(),sha(f)) for f in files]
            protected[rel]=sha_bytes(json.dumps(entries,separators=(',',':')).encode())
    if protected!=prior.get('protected_content_before_sha256'):
        fail('protected wiki content differs from the preceding preceding PR89 receipt')
    OUT.mkdir(parents=True,exist_ok=True)
    if delegated_importer_bindings()!=delegated_pins:
        fail('delegated Graphify/KG updater sources changed after planning')
    sys.path.insert(0,str(OLD_PUBLISH))
    updater_spec=importlib.util.spec_from_file_location('pr59_publish_update',DELEGATED_UPDATER)
    graph_update=importlib.util.module_from_spec(updater_spec)
    sys.modules[updater_spec.name]=graph_update
    updater_spec.loader.exec_module(graph_update)
    graph_update.SOURCE=SOURCE;graph_update.OUT=OUT;graph_update.BASE_COMMIT=BASE;graph_update.PR=PR
    graph_update.PATHS=tuple(x['path'] for x in items)
    spec=importlib.util.spec_from_file_location('pr59_audit_util',DELEGATED_AUDITOR)
    audit=importlib.util.module_from_spec(spec);sys.modules[spec.name]=audit;spec.loader.exec_module(audit)
    audit.ROOT=ROOT;audit.MAINTAINED=MAINT;audit.OUT=OUT;audit.PATHS=tuple(x['path'] for x in items)
    # Guard every destination the delegated Graphify/writer batch may create.
    for directory in (ROOT,MAINT):
        for rel in graph_update.GRAPH_FILES:
            guard_destination(directory/'graphify-out'/rel,directory)
        for name in ('graph.json','GRAPH_REPORT.md','manifest.json'):
            guard_destination(directory/'graphify-out'/SNAPSHOT/name,directory)
    for rel in graph_update.WIKI_FILES:guard_destination(ROOT/'wiki'/rel)
    before={label:json.loads((directory/'graphify-out/graph.json').read_text()) for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT))}
    # Back up every graph/report/manifest and allowed wiki artifact before mutation.
    baseline_presence={}
    rollback_backup_sha256={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        for rel in graph_update.GRAPH_FILES:
            p=directory/'graphify-out'/rel
            baseline_presence[str(p)]=p.exists()
            if p.exists():
                regular_file(p)
                target=OUT/'backups'/label/rel;target.parent.mkdir(parents=True,exist_ok=True);copy_checked(p,target)
                rollback_backup_sha256[str(target)]=sha(target)
    for rel in graph_update.WIKI_FILES:
        p=ROOT/'wiki'/rel
        baseline_presence[str(p)]=p.exists()
        if p.exists():
            regular_file(p)
            target=OUT/'backups/wiki'/rel;target.parent.mkdir(parents=True,exist_ok=True);copy_checked(p,target)
            rollback_backup_sha256[str(target)]=sha(target)
    dated_names=('graph.json','GRAPH_REPORT.md','manifest.json')
    dated_before={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        dated_before[label]={}
        for name in dated_names:
            p=directory/'graphify-out'/SNAPSHOT/name
            target=OUT/'backups'/label/f'dated_{SNAPSHOT}'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            existed=p.exists()
            if existed:
                copy_checked(p,target)
                rollback_backup_sha256[str(target)]=sha(target)
            dated_before[label][name]={'path':str(p),'before_sha256':sha(p) if existed else None,'backup_path':str(target),'existed_before':existed}
    automatic_snapshot_backups={}
    for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
        previous=directory/'graphify-out/2026-10-19'
        if not previous.exists():
            continue
        guard_directory(previous,directory)
        members={}
        for original in sorted(previous.iterdir()):
            guard_destination(original,directory)
            backup=OUT/'backups'/label/'prior_auto_2026-10-19'/original.name
            backup.parent.mkdir(parents=True,exist_ok=True)
            copy_checked(original,backup)
            members[original.name]={'backup':str(backup),'sha256':sha(backup)}
        automatic_snapshot_backups[str(previous)]=members
    sync={'base_commit':BASE,'frozen_commit':args.commit,'paths':items}
    source_sync_path=OUT/'source_sync.json'
    guard_destination(source_sync_path)
    source_sync_path.write_text(json.dumps(sync,indent=2)+'\n')
    try:
        records={'KLAPS50':graph_update.update_graph('KLAPS50',ROOT,'Cloud-BAL',items),
                 'Cloud-BAL':graph_update.update_graph('Cloud-BAL',MAINT,'',items)}
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            ext=json.loads((OUT/f'{label.lower().replace("-","_")}_extraction.json').read_text())
            audit.record_snapshot(label,directory,before[label],ext)
        # Preserve every old date-directory member, including hidden labels/analysis.
        restore_automatic_snapshots(automatic_snapshot_backups)
        private=audit.verify_private_profile(before)
        if private['Cloud-BAL']['nodes']!=134 or private['Cloud-BAL']['incident_links']!=133 or not private['Cloud-BAL']['unchanged'] or private['KLAPS50']['nodes']!=0:
            fail('private profile preservation guard failed')
        if git('rev-parse','HEAD')!=args.commit or git('status','--porcelain'):fail('source checkout changed during graph build')
        for x in items:
            if sha(SOURCE/x['path'])!=x['candidate_sha256']:fail(f'candidate source changed during build: {x["path"]}')
            p=MAINT/x['path'];guard_destination(p,MAINT);after=sha(p) if p.is_file() else None
            if after!=x['maintained_before_sha256']:fail(f'maintained source path changed: {x["path"]}')
        for label,r in records.items():
            r['previous_graph_sha256']=prior['corpora'][label]['sha256']
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            report_path=directory/'graphify-out/GRAPH_REPORT.md'
            guard_destination(report_path,directory)
            old_report=report_path.read_text()
            new_section=(f"## Graph Freshness\n\n"
                f"- Selected candidate overlay: `{args.commit}` against `{BASE}`; "
                f"{len(items)} committed changed paths hash-bound, {sum(x['graphify_extraction']=='AST_OR_MARKDOWN_HEADING' for x in items)} structurally extractable.\n"
                f"- Non-extractable selected artifacts remain hash-bound in the receipt and are not parsed.\n"
                f"- Snapshot: {records[label]['snapshot']}. Maintained checkout HEAD is a separate base, "
                f"not the source identity of this selected extraction.\n"
                f"- The persistent graph combines earlier corpus snapshots and selected overlays. "
                f"This is not a full extraction of the candidate tree.\n"
                f"- AST/Markdown headings only; cross-file Fortran CALL extraction is partial. "
                f"Freshness is navigation evidence, not runtime/scientific validation.\n"
                f"- External source trees and runtime artifacts outside the selected repository paths are not represented.\n")
            new_report,count=re.subn(r"## Graph Freshness\n.*?(?=\n## |\Z)",new_section,old_report,flags=re.S)
            if count!=1:fail(f'{label} derived freshness section missing or duplicated')
            report_path.write_text(new_report)
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for name in dated_names:
                source=directory/'graphify-out'/name
                target=directory/'graphify-out'/SNAPSHOT/name
                guard_destination(target,directory)
                target.parent.mkdir(parents=True,exist_ok=True)
                copy_checked(source,target)
                dated_before[label][name]['after_sha256']=sha(target)
                if sha(source)!=sha(target):fail(f'{label} final dated copy differs: {name}')
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            records[label]['snapshot']=datetime.fromtimestamp((directory/'graphify-out/GRAPH_REPORT.md').stat().st_mtime,timezone.utc).isoformat()
        copy_checked(ROOT/'graphify-out/GRAPH_REPORT.md',ROOT/'wiki/graph-report-klaps50.md')
        copy_checked(MAINT/'graphify-out/GRAPH_REPORT.md',ROOT/'wiki/graph-report-cloud-bal.md')
        idx=ROOT/'wiki/graph-report.md';lines=idx.read_text().splitlines()
        for i,line in enumerate(lines):
            for label,r in records.items():
                if line.startswith(f'| {label} |'):
                    folder='.' if label=='KLAPS50' else 'Cloud-BAL/';mirror='graph-report-klaps50' if label=='KLAPS50' else 'graph-report-cloud-bal'
                    lines[i]=f"| {label} | `{folder}` | {r['snapshot']} (PR90 rain-roundtrip candidate overlay) | {r['nodes']} | {r['edges']} | {r['communities']} | [[{mirror}]] |"
        guard_destination(idx)
        idx.write_text('\n'.join(lines)+'\n')
        page=ROOT/'wiki/index.md';before_text=page.read_text();start=before_text.index('## Graph snapshot');end=before_text.find('\n## ',start+3);has_tail=end>=0
        if not has_tail:end=len(before_text)
        section='## Graph snapshot\n\n'
        for label,r in records.items():
            section+=(f"- {label}: {r['snapshot']}; {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; "
              f"PR90 rain-roundtrip overlay delta [{r['delta_nodes']}, {r['delta_edges']}].\n")
        section+='- [[graph-report|Separate corpus reports]] retain extraction limits. Graph freshness is navigation evidence only, not runtime or scientific validation.\n'
        after_text=before_text[:start]+section+before_text[end:]
        if before_text[:start]!=after_text[:start]:fail('index prefix changed outside Graph snapshot section')
        if has_tail:
            new_end=after_text.find('\n## ',after_text.index('## Graph snapshot')+3)
            if new_end<0 or before_text[end:]!=after_text[new_end:]:fail('index suffix changed outside Graph snapshot section')
        guard_destination(page)
        after_text=re.sub(r'(?m)^date_modified: .*$', 'date_modified: 2026-10-19', after_text, count=1)
        page.write_text(after_text)
        stamp=datetime.now(timezone.utc)
        log=ROOT/'wiki/log.md'
        entry=f"\n## [{stamp.strftime('%Y-%m-%d')}] kg-update | PR90 rain-roundtrip selected-path overlay ({stamp.strftime('%H:%M UTC')})\n"
        entry+=f"- PR {PR}; frozen source commit `{args.commit}` against `{BASE}`. {len(items)} committed changed paths were hash-captured; {sum(x['graphify_extraction']=='AST_OR_MARKDOWN_HEADING' for x in items)} supported files were structurally extracted. Non-extractable selected artifacts are hash-only. Maintained source files were not copied or replaced.\n"
        for label,r in records.items():
            entry+=(f"- {label} snapshot {r['snapshot']}: {r['nodes']} nodes / {r['edges']} edges / {r['communities']} communities; "
              f"PR90 rain-roundtrip overlay delta [{r['delta_nodes']}, {r['delta_edges']}], added/removed IDs {r['added_ids']}/{r['removed_ids']}; "
              f"previous graph SHA-256 `{r['previous_graph_sha256']}`.\n")
        entry+='- Cloud-BAL private profile remains 134 nodes / 133 incident links; KLAPS50 carries zero nodes from this private source. Graph integrity diagnostics passed.\n'
        entry+='- Graphify 0.9.53 selected-source AST/Markdown-heading extraction and separate `cluster-only --no-viz --no-label`; no semantic refresh. Generated Fortran inside Python strings and compressed sources is not separately Fortran-AST extracted. Cross-file Fortran CALL extraction is partial; corpora overlap and counts are separate.\n'
        entry+=f"- Graph freshness is navigation-only; selected-source AST/Markdown headings have no semantic refresh, and cross-file Fortran CALL extraction is partial. Physical approval carries forward `{prior['physical_approval']}`.\n"
        entry+=f"- Durable preceding PR89 KG receipt: `{PRIOR.relative_to(ROOT)}` (SHA-256 `{PRIOR_SHA}`); its immutable prior-receipt chain remains pinned.\n"
        if validation:
            entry+=f"- Validation evidence: {validation['summary']} Receipt `{validation['path']}` SHA-256 `{validation['sha256']}` at `{args.commit}`.\n"
        else:
            entry+='- No separate CP06A authority receipt is supplied; runtime and scientific statuses are bound below from the integration receipt.\n'
        entry+=f"- Overall physical approval remains `{prior['physical_approval']}`. PR90 rain-roundtrip and scientific status fields are taken from the bound final integration receipt; graph freshness does not establish runtime or scientific acceptance.\n"
        entry+=f"- PR90 integration statuses are bound from `{INTEGRATION_PATH}` (SHA-256 `{integration['sha256']}`); graph freshness establishes no physical or scientific acceptance.\n"
        current=integration['document']
        runtime=current['latest_actual_host']
        windows=runtime.get('windows',{})
        window_status={duration:{'status':row.get('status'),
          'arms':{arm:{key:arm_row.get(key) for key in ('status','returncode','final_completed_step')}
                  for arm,arm_row in row.get('arms',{}).items()}}
          for duration,row in windows.items()}
        runtime_status=runtime.get('status','STATUS_RECORDED')
        entry+=f"- Runtime status: `{runtime_status}`; per-window arm statuses {json.dumps(window_status,sort_keys=True)}.\n"
        entry+=f"- Candidate scientific gates remain separate from runtime status: {json.dumps(current['candidate_scientific_gates'],sort_keys=True)}; physical approval stays FAIL_OPEN.\n"
        validation_status=current.get('validation',{}).get('status',validation['document'].get('status','STATUS_RECORDED'))
        entry+=f"- Focused validation status: `{validation_status}`. No model physics acceptance is inferred from graph freshness.\n"
        guard_destination(log)
        with log.open('a') as f:f.write(entry)
        for rel,expected in protected.items():
            p=ROOT/rel
            if p.is_file():
                guard_destination(p)
                if sha(p)!=expected:fail(f'protected wiki file changed: {rel}')
            else:
                guard_directory(p)
                files=sorted(x for x in p.rglob('*') if x.is_file())
                for q in files:guard_destination(q)
                rows=[(q.relative_to(ROOT).as_posix(),sha(q)) for q in files]
                if sha_bytes(json.dumps(rows,separators=(',',':')).encode())!=expected:fail(f'protected wiki directory changed: {rel}')
        maintained_after=maintained_source_snapshot()
        if maintained_after!=maintained_before:fail('maintained non-graph source, wiki content, profile, or prior receipt changed during Graphify refresh')
        maintained_snapshot_verified=True
        for p,h in immutable.items():
            if p!=HELPER:guard_destination(p,Path('/var/tmp') if p.parent==Path('/var/tmp') else ROOT)
            if sha(p)!=h:fail(f'prior immutable receipt changed: {p}')
        receipt={
          'schema':'pr90_rain_roundtrip_selected_path_graphify_kg_receipt_v1','dated_snapshot_day':'2026-10-19','dated_snapshot_timezone':'Asia/Seoul (session day)','recorded_utc':datetime.now(timezone.utc).isoformat(),
          'pr':PR,'base_commit':BASE,'frozen_source_commit':args.commit,'source_path':str(SOURCE),'selected_path_count':len(items),
          'selected_paths':items,'non_extractable_selected_paths':[x['path'] for x in items if x['graphify_extraction']=='NON_EXTRACTABLE_HASH_ONLY'],'source_sync_sha256':sha(OUT/'source_sync.json'),
          'maintained_source_snapshot':{'verified_pre_post_equal':maintained_snapshot_verified,
            'entry_count':len(maintained_before),'symlink_entries':sum(v.get('kind')=='symlink' for v in maintained_before.values()),'before_sha256':maintained_before_digest,
            'scope':'active src/, tests/, docs/, config/ in KLAPS50 and Cloud-BAL; immediate tracked root files; remaining wiki content is separately protected by page/directory hashes',
            'excluded':'scratch/worktrees, .git, graphify-out, and the five intentionally refreshed derived wiki files (three graph reports, index.md, log.md)'},
          'previous_pr89_kg_receipt_sha256':PRIOR_SHA,
          'previous_pr89_kg_receipt_path':str(PRIOR),
          'previous_pr89_source_commit':prior['frozen_source_commit'],
          'previous_physical_approval':prior['physical_approval'],
          'physical_approval':prior['physical_approval'],
          'remaining_scientific_gates':prior.get('remaining_scientific_gates',[]),
          'remaining_acceptance_gates':INHERITED_ACCEPTANCE_GATES,
          'same_candidate_integration_conditions_open':OPEN_SAME_CANDIDATE_INTEGRATION_CONDITIONS,
          'validation_receipt_binding':validation,
          'native_receipt_binding':native_binding,
          'closed_runtime_binding':native_binding['closed_runtime'],
          'delegated_importer_pins':delegated_pins,
          'candidate_scientific_gates':pending_candidate_gates,
          'graphify_version':subprocess.check_output(['graphify','--version'],text=True).strip(),'python_executable':sys.executable,
          'mode':'guarded selected-path overlay extraction/build_merge, cluster-only, derived wiki sync',
          'extraction':'Graphify AST and Markdown headings only; no semantic/LLM refresh; unsupported/binary selected files are hash-bound but not parsed',
          'corpora':records,'private_profile_preservation':private,
          'dated_snapshots':dated_before,'dated_snapshot_directory':SNAPSHOT,
          'automatic_snapshot_preservation':automatic_snapshot_backups,'baseline_artifact_presence':baseline_presence,
          'rollback_backup_sha256':rollback_backup_sha256,'protected_content_before_sha256':protected,
          'wiki':{'updated':['graph-report.md','graph-report-klaps50.md','graph-report-cloud-bal.md','index.md#Graph-snapshot','log.md (append-only)'],
            'protected_unchanged':list(protected),'schema_and_content_pages_touched':False},
          'prior_immutable_receipts':{str(p):h for p,h in immutable.items()},
          'limitations':['Graph counts are separate for overlapping KLAPS50 and Cloud-BAL corpora.','Markdown semantic extraction was not performed; Markdown contributes heading structure only.',
            'Fortran cross-file CALL extraction is partial.','Generated Fortran inside Python strings and compressed source artifacts is hash-bound, not separately Fortran-AST extracted.','External source trees and runtime artifacts outside selected repository paths are not represented.',
            'Candidate overlay graphs and freshness are structural navigation evidence, not runtime or scientific validation.',
            'Non-extractable or binary selected paths are recorded by SHA-256 and passed to the pinned Graphify extractor, which returns no extractor for their suffix; their contents are not parsed.',
            'The preceding PR89 receipt chain remains immutable; this structural update does not establish end-to-end runtime or scientific acceptance.']}
        receipt['wiki_sha256']={rel:sha(ROOT/rel) for rel in ('wiki/graph-report.md','wiki/graph-report-klaps50.md','wiki/graph-report-cloud-bal.md','wiki/index.md','wiki/log.md')}
        rp=OUT/'kg_receipt.json';guard_destination(rp);rp.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
        print(json.dumps({'receipt':str(rp),'receipt_sha256':sha(rp),'corpora':records,'private_profile':private},indent=2))
    except BaseException as original_error:
        rollback_errors=[]
        def attempt_restore(label,operation):
            try:operation()
            except BaseException as error:
                rollback_errors.append(f'{label}: {type(error).__name__}: {error}')

        def restore_artifact(backup,target,existed_before):
            if existed_before:
                if not backup.exists():fail(f'rollback backup missing: {backup}')
                if sha(backup)!=rollback_backup_sha256[str(backup)]:
                    fail(f'rollback backup changed: {backup}')
                copy_checked(backup,target)
            elif target.exists():
                guard_destination(target);target.unlink()

        attempt_restore('prior automatic snapshots',
                        lambda:restore_automatic_snapshots(automatic_snapshot_backups))
        for label,directory in (('KLAPS50',ROOT),('Cloud-BAL',MAINT)):
            for rel in graph_update.GRAPH_FILES:
                backup=OUT/'backups'/label/rel;target=directory/'graphify-out'/rel
                attempt_restore(str(target),lambda b=backup,t=target:
                    restore_artifact(b,t,baseline_presence[str(t)]))
            for name in dated_names:
                backup=OUT/'backups'/label/f'dated_{SNAPSHOT}'/name
                target=directory/'graphify-out'/SNAPSHOT/name
                existed=dated_before[label][name]['existed_before']
                attempt_restore(str(target),lambda b=backup,t=target,e=existed:
                    restore_artifact(b,t,e))
            new_snapshot=directory/'graphify-out'/SNAPSHOT
            def remove_empty_snapshot(path=new_snapshot,root=directory):
                if path.exists():
                    guard_directory(path,root)
                    if not any(path.iterdir()):path.rmdir()
            # Unexpected concurrent files remain untouched; restoration continues.
            attempt_restore(str(new_snapshot),remove_empty_snapshot)
        for rel in graph_update.WIKI_FILES:
            backup=OUT/'backups/wiki'/rel;target=ROOT/'wiki'/rel
            attempt_restore(str(target),lambda b=backup,t=target:
                restore_artifact(b,t,baseline_presence[str(t)]))

        def verify_restored_sources():
            if maintained_source_snapshot()!=maintained_before:
                fail('rollback did not preserve maintained source/wiki/profile content')
            if git('rev-parse','HEAD')!=args.commit or git('status','--porcelain'):
                fail('candidate source worktree changed during failed graph build')
            for selected in items:
                if sha(SOURCE/selected['path'])!=selected['candidate_sha256']:
                    fail(f'candidate source bytes changed: {selected["path"]}')
        attempt_restore('source preservation',verify_restored_sources)
        for pinned_path,pinned_sha in immutable.items():
            def verify_immutable(path=pinned_path,digest=pinned_sha):
                if sha(path)!=digest:fail(f'rollback changed an immutable prior pin: {path}')
            attempt_restore(str(pinned_path),verify_immutable)
        if rollback_errors:
            raise RuntimeError('KG update failed; rollback also reported: '+'; '.join(rollback_errors)) from original_error
        raise

if __name__=='__main__':main()
