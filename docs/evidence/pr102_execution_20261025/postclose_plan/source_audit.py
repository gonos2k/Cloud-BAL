#!/usr/bin/env python3
"""Run pinned PR93 source-policy predicates against one closed PR102 C2 run."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL')
RUN_ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/pr102_native_structure640_20261025/STRUCTURED640_RUN')
WRAPPER = REPO / 'tools/pr98_boundary_audit.py'
OUTPUT = RUN_ROOT.parent / 'source_policy_audit.json'
PLAN = Path('/var/tmp/pr102_structured640_postclose_source_audit_plan_v3.json')
EXECUTION_PREFLIGHT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL/docs/evidence/pr102_execution_20261025/preflight.json')
EXPECTED = {
    'base_executable_sha256': '387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a',
    'input_sha256': 'b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f',
    'boundary_sha256': '885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7',
    'namelist_sha256': '58c194b8846d25a6c7cbfedac1477fbf65fcc1a12705c8cb11851096ee7d2fc8',
    'build_receipt_sha256': '9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb',
    'runner_sha256': '35adaa773773c046311d731ea1426821befb225a444092405098b4ee4e8baa43',
    'wrapper_sha256': '77f911b4e4b552cc92c47885c3f7c875cad7028636fb06d9b8ec463e79282932',
    'closed_reader_sha256': '8f9affa02e6d843d623911cfd6a9447a9ddb4ba0713cf927e2d5de2bcfb2e126',
    'response_sha256': '9e30de564c85b5cfdbb8c9141d3f86f68d2958582892c62ad7578c77affe866e',
    'execution_preflight_sha256': 'c58feba119b7c774dc2b37e416bb6a46d49cdadfba104c7ef5c469faf5592dea',
}

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

sys.path.insert(0, str(REPO / 'tools'))
import pr102_response as response
spec = importlib.util.spec_from_file_location('pr102_pinned_source_audit_wrapper', WRAPPER)
if spec is None or spec.loader is None:
    raise RuntimeError('cannot load pinned audit wrapper')
wrapper = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = wrapper
spec.loader.exec_module(wrapper)
reader_pins = wrapper.verify_reader_pins()
closed = wrapper.load_closed_auditor()
receipt_path = RUN_ROOT / 'receipt.json'
if not receipt_path.is_file():
    raise RuntimeError('run receipt is not closed; source audit is deferred')
receipt = json.loads(receipt_path.read_text())
if (receipt.get('arm') != 'STRUCTURED' or receipt.get('status') != 'COMPLETE' or
        receipt.get('returncode') != 0 or receipt.get('final_completed_step') != 32 or
        receipt.get('fatal_lines') or receipt.get('processing_errors')):
    raise RuntimeError('run is not receipt-closed COMPLETE/32 with no fatal or processing errors')
build = receipt.get('candidate_build') or {}
if (receipt.get('candidate_wrfinput_sha256') != EXPECTED['input_sha256'] or
        receipt.get('candidate_wrfbdy_sha256') != EXPECTED['boundary_sha256'] or
        receipt.get('candidate_namelist_sha256') != EXPECTED['namelist_sha256'] or
        receipt.get('executed_executable_sha256') != EXPECTED['base_executable_sha256'] or
        receipt.get('expected_executed_executable_sha256') != EXPECTED['base_executable_sha256'] or
        build.get('receipt_sha256') != EXPECTED['build_receipt_sha256'] or
        build.get('executable_sha256') != EXPECTED['base_executable_sha256']):
    raise RuntimeError('closed run does not match the pinned C2 executable/input/boundary/namelist/build')
source_pins_before = {str(path): sha(path) for path in
                      (Path(__file__).resolve(), WRAPPER,
                       Path('/var/tmp/pr102_capture20_runner_bundle_v2_20261025/tools/pr86_time_response.py'),
                       REPO / 'tools/pr102_response.py', EXECUTION_PREFLIGHT)}
plan = json.loads(PLAN.read_text())
if plan.get('executor', {}).get('path') != str(Path(__file__).resolve()) or \
        plan.get('executor', {}).get('sha256') != source_pins_before[str(Path(__file__).resolve())]:
    raise RuntimeError('post-close source audit plan does not pin this executor')
reader_chain_before = {row['path']: sha(Path(row['path'])) for row in plan['source_reader_chain']}
if any(reader_chain_before[row['path']] != row['sha256'] for row in plan['source_reader_chain']):
    raise RuntimeError('post-close source reader chain changed since plan review')
if (source_pins_before[str(WRAPPER)] != EXPECTED['wrapper_sha256'] or
        source_pins_before[str(Path('/var/tmp/pr102_capture20_runner_bundle_v2_20261025/tools/pr86_time_response.py'))] != EXPECTED['runner_sha256'] or
        source_pins_before[str(REPO / 'tools/pr102_response.py')] != EXPECTED['response_sha256'] or
        source_pins_before[str(EXECUTION_PREFLIGHT)] != EXPECTED['execution_preflight_sha256'] or
        sha(Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/pr102_wind_structure_20261025/Cloud-BAL/docs/evidence/pr93_active_ice_20261020/runtime/closed_run_audit.py')) != EXPECTED['closed_reader_sha256']):
    raise RuntimeError('source audit executor/wrapper/runner/closed-reader pin changed')
execution_preflight = json.loads(EXECUTION_PREFLIGHT.read_text())
response._verify_execution_preflight(execution_preflight)
structured, run_preflight = response._closed_structured_run(RUN_ROOT, execution_preflight)
preflight_binding = run_preflight.get('pr102_execution_preflight', {})
if (preflight_binding.get('path') != str(EXECUTION_PREFLIGHT) or
        preflight_binding.get('sha256') != EXPECTED['execution_preflight_sha256']):
    raise RuntimeError('closed run preflight does not bind the pinned PR102 execution preflight')
if OUTPUT.exists():
    raise FileExistsError(f'refusing to overwrite {OUTPUT}')
report = closed.audit_arm(RUN_ROOT, 'STRUCTURED')
source_pins_after = {str(path): sha(path) for path in
                     (Path(__file__).resolve(), WRAPPER,
                      Path('/var/tmp/pr102_capture20_runner_bundle_v2_20261025/tools/pr86_time_response.py'),
                      REPO / 'tools/pr102_response.py', EXECUTION_PREFLIGHT)}
reader_chain_after = {row['path']: sha(Path(row['path'])) for row in plan['source_reader_chain']}
if source_pins_after != source_pins_before or reader_chain_after != reader_chain_before:
    raise RuntimeError('source audit chain changed during the audit')
record = {
    'schema': 'pr102_structured640_source_policy_audit_v1',
    'run_receipt': {'path': str(receipt_path), 'sha256': sha(receipt_path)},
    'run_preflight': {'path': str(RUN_ROOT / 'preflight.json'), 'sha256': sha(RUN_ROOT / 'preflight.json')},
    'pr102_execution_preflight': {'path': str(EXECUTION_PREFLIGHT), 'sha256': sha(EXECUTION_PREFLIGHT)},
    'runner_source': {'path': str(Path('/var/tmp/pr102_capture20_runner_bundle_v2_20261025/tools/pr86_time_response.py')),
                      'sha256': sha(Path('/var/tmp/pr102_capture20_runner_bundle_v2_20261025/tools/pr86_time_response.py'))},
    'source_audit_wrapper': {'path': str(WRAPPER), 'sha256': sha(WRAPPER)},
    'reader_pins': reader_pins,
    'source_pins_before': source_pins_before,
    'source_pins_after': source_pins_after,
    'reader_chain_before': reader_chain_before,
    'reader_chain_after': reader_chain_after,
    'diagnostic_source_authority': {
        'base_c2_executable_sha256': receipt.get('baseline_frozen_executable_sha256'),
        'executed_executable_sha256': receipt.get('executed_executable_sha256'),
        'candidate_input_sha256': receipt.get('candidate_wrfinput_sha256'),
        'candidate_build': receipt.get('candidate_build'),
    },
    'report': report,
}
OUTPUT.write_text(json.dumps(record, indent=2, sort_keys=True) + '\n')
print(json.dumps({
    'schema': record['schema'],
    'status': 'AUDIT_RECORDED_WITH_SEPARATE_GATES',
    'generic_qnb': report.get('qnb_pair_conversion_audit', {}).get('status'),
    'exact_source_endpoint': report.get('exact_source_endpoint_audit', {}).get('status'),
    'active_ice_policy': report.get('active_ice_policy_split', {}).get('status'),
    'output': str(OUTPUT),
}, indent=2))
