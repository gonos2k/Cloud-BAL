#!/usr/bin/env python3
"""Score the frozen input-only weak/strong QSNOW gate experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import math
import shutil
import sys
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path

import numpy as np
import netCDF4

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = ROOT / 'docs/evidence/weak_strong_balance_20261030'
PLAN_PATH = EVIDENCE_DIR / 'selection_plan.json'
PLAN_SHA256 = '17e8833f2f28da76e1474f82440a88889bd55ba723ef9cd6618d06a0eb786248'
RUNTIME_DIR = EVIDENCE_DIR / 'runtime'
COMMON_PLAN_SHA256 = 'a2d06679ea3a9b24a04f9ff359c842172f06fd7ec0f402f802c91399b2ad6a3a'
PRIOR_ANALYSIS = ROOT / 'docs/evidence/snow_lower_20261030/analysis'
PRIOR_RECEIPT_SHA256 = 'a9b8fa97e12d85bd49ce91b42f5126c8fc727ef0846eba1eeddc6a552a044602'
PRIOR_COMMON_PLAN = ROOT / 'docs/evidence/snow_lower_20261030/runtime/common_plan.json'
PRIOR_COMMON_PLAN_SHA256 = '58dae266e4b4f893f5a9d940e30c8e38574823b03785e68b089811ef9d085871'
PRIOR_CATEGORICAL_SHA256 = '3dcab1e1ca19b3bce65611a3196eeaa93ae0c23560f00145ccfbd6b0fd170c7b'
PRIOR_CONTINUOUS_SHA256 = '3c00bfc8680387b953909fbccec4ab1be1a3696929c31dcc708b584f418a3d46'
PRIOR_TOOL = ROOT / 'tools/cp02_snow_lower.py'
PRIOR_TOOL_SHA256 = '04108676ffe44db688ee53a24ee07fdb2031a0d9fd4012f17619a6245c03d3c2'
PRIOR_EXTENSION = ROOT / 'tools/cp02_snow_extension.py'
PRIOR_EXTENSION_SHA256 = 'b450747f0d376a353eff8c33da7ebbddfedc5d137fa9e53e0b37f0e71907da86'
PRIOR_SENSITIVITY = ROOT / 'tools/cp02_snow_sensitivity.py'
PRIOR_SENSITIVITY_SHA256 = '95c3e8591318eafda06598616fdec1c11f67aa78aef3306ab473a1602ccadc17'
SIX_HOUR_TOOL = ROOT / 'tools/cp02_six_hour_improvement.py'
CASE_IDS = ('GATE_G50_90', 'EQ_G50_90', 'GATE_G75_95', 'EQ_G75_95',
            'GATE_G90_99', 'EQ_G90_99', 'FIXED_ORIGINAL_100', 'ORIGINAL_B1_100')
REFERENCE_IDS = ('ORIGINAL', 'CONTROL_SNOW_300', 'IMPROVED_BG_FIXED', 'IMPROVED_SNOW_080')
CONTEXT_IDS = REFERENCE_IDS + CASE_IDS
GATE_PAIRS = (('GATE_G50_90', 'EQ_G50_90'), ('GATE_G75_95', 'EQ_G75_95'),
              ('GATE_G90_99', 'EQ_G90_99'))
FACTORIAL_CASES = ('ORIGINAL', 'FIXED_ORIGINAL_100', 'ORIGINAL_B1_100', 'IMPROVED_BG_FIXED')
HOURS = tuple(range(13, 19))
THRESHOLDS = (0.1, 0.5, 1.0, 2.5, 5.0, 10.0)
WEAK_THRESHOLDS = (0.1, 0.5, 1.0)
INTENSITY_BINS = (('dry', 0.0, 0.1), ('light', 0.1, 1.0), ('moderate', 1.0, 5.0),
                  ('strong', 5.0, 10.0), ('very_strong', 10.0, None))
POINTS = 3688
HISTORY_NAMES = tuple(f'wrfout_d01_2026-08-16_{hour:02d}:00:00' for hour in range(12, 19))
ORIGINAL_EXECUTABLE_SHA256 = 'de110a7f1d40143a74ffedbe64ed5b3717c413876093f56d200563e2f6b9c168'
FIXED_EXECUTABLE_SHA256 = '68ed2833b5f207d037949c9b20c7c2f800500e632f911a4acf1eb09d13bf1c1f'
ORIGINAL_INPUT_SHA256 = '5d6b2bdce4121642dea994f3e953cca690ad7c9f52f6f8feb01bb6c2f0b9b6bc'
B1_INPUT_SHA256 = '9f8b494dbf5ce765e4320701475d6a65be1f591d72a4f9bf5e929c208be563e5'
BOUNDARY_SHA256 = '74102ac2063f17a9007f3352e6e6c2f52629055bdf3f05b4f4d6d77aef835f45'
NAMELIST_SHA256 = 'eced598028b71b996c0c22cf7bd4bacb067087575ec06c4b65d71ab4913156df'
INTEL_PROFILE_SHA256 = '5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4'
INTEL_MPI_VERSION = 'Intel(R) MPI Library for Linux* OS, Version 2021.18.0 Build 20260327 (id: 821f207)'
ORIGINAL_INPUT_PATH = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/current_forecast_paper_20261029/run.PomEr8/original/wrfinput_d01')
B1_INPUT_PATH = Path('/var/tmp/six-hour-improved-runtime-20261030/IMPROVED_BG_FIXED/wrfinput_d01')
GATE_MAP_PATH = RUNTIME_DIR / 'frozen/initial_precip_gate_maps.npz'
GATE_MANIFEST_PATH = RUNTIME_DIR / 'frozen/gate_manifest.json'


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def identity(path: Path) -> dict:
    path = Path(path)
    return {'path': str(path), 'sha256': sha256(path), 'size_bytes': path.stat().st_size}


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load module: {path}')
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def native_value_hash(variable) -> str:
    values = np.asanyarray(variable[:])
    digest = hashlib.sha256()
    digest.update(str(values.dtype).encode())
    digest.update(json.dumps(list(values.shape)).encode())
    if np.ma.isMaskedArray(values):
        digest.update(np.ascontiguousarray(np.ma.getmaskarray(values)).tobytes())
        values = np.ma.getdata(values)
    digest.update(np.ascontiguousarray(values).tobytes())
    return digest.hexdigest()


def audit_native_inputs(common: dict, runtime_dir: Path):
    """Recheck each staged NetCDF field against source or the frozen 2-D gate map."""
    helper_path = ROOT / 'tools/initial_precip_gate.py'
    helper_record = identity(helper_path)
    gate_helper = load_module('initial_precip_gate_audit', helper_path)
    map_path, manifest_path = Path(common['gate_map_path']), Path(common['gate_manifest_path'])
    map_record, manifest_record = identity(map_path), identity(manifest_path)
    if (map_record['sha256'] != common.get('gate_map_sha256')
        or manifest_record['sha256'] != common.get('gate_manifest_sha256')):
        raise ValueError('frozen input-only gate map or manifest hash mismatch')
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    if (manifest.get('source_wrfinput_sha256') != ORIGINAL_INPUT_SHA256
        or manifest.get('forecast_output_or_observation_used') is not False
        or common.get('gate_manifest') != manifest):
        raise ValueError('gate manifest source/input-only contract mismatch')
    with np.load(map_path, allow_pickle=False) as archive:
        maps = {key: np.asarray(archive[key]) for key in archive.files}
    with netCDF4.Dataset(ORIGINAL_INPUT_PATH) as original:
        proxy, geometry = gate_helper.column_precip_proxy(original)
        source_qsnow = np.asarray(original.variables['QSNOW'][0])
        latitude = np.asarray(original.variables['XLAT'][0], dtype=np.float64)
        longitude = np.asarray(original.variables['XLONG'][0], dtype=np.float64)
    with netCDF4.Dataset(B1_INPUT_PATH) as b1:
        b1_qsnow = np.asarray(b1.variables['QSNOW'][0])
    if sha256(ORIGINAL_INPUT_PATH) != ORIGINAL_INPUT_SHA256:
        raise ValueError('ORIGINAL input changed during native audit')
    if sha256(B1_INPUT_PATH) != B1_INPUT_SHA256:
        raise ValueError('B1 input changed during native audit')
    expected_map_keys = {'proxy', 'latitude', 'longitude'}
    if not np.array_equal(maps.get('latitude'), latitude) or not np.array_equal(maps.get('longitude'), longitude):
        raise ValueError('frozen map coordinates differ from the source input XLAT/XLONG')
    for suffix in ('G50_90', 'G75_95', 'G90_99'):
        expected_map_keys.update({f'{suffix}_alpha', f'{suffix}_qsn_gated',
                                  f'{suffix}_qsn_equal_mass', f'{suffix}_alpha_equal_mass',
                                  f'{suffix}_source_qsn_column_kg_m2',
                                  f'{suffix}_gate_qsn_column_kg_m2',
                                  f'{suffix}_eq_qsn_column_kg_m2',
                                  f'{suffix}_gate_added_qsn_column_kg_m2',
                                  f'{suffix}_eq_added_qsn_column_kg_m2'})
        alpha, thresholds = gate_helper.gate_alpha(proxy, *gate_helper.QUANTILE_PAIRS[suffix])
        if not np.array_equal(maps[f'{suffix}_alpha'], alpha):
            raise ValueError(f'{suffix}: frozen alpha map differs from independent input-only calculation')
        if not np.array_equal(maps[f'{suffix}_qsn_gated'], gate_helper.scaled_qsnow(source_qsnow, alpha)):
            raise ValueError(f'{suffix}: frozen gate QSNOW differs from its 2-D alpha transform')
        equal_alpha, equal_qsnow, mass = gate_helper.equal_mass_alpha(
            source_qsnow, maps[f'{suffix}_qsn_gated'], geometry['dry_mass_kg'])
        if (not np.array_equal(maps[f'{suffix}_qsn_equal_mass'], equal_qsnow)
            or not np.array_equal(maps[f'{suffix}_alpha_equal_mass'],
                                  np.full(proxy.shape, equal_alpha, dtype=np.float64))
            or mass['relative_mass_difference'] > 1e-6):
            raise ValueError(f'{suffix}: frozen equal-mass QSNOW differs from the matched transform')
        source_column = np.sum(source_qsnow.astype(np.float64) * geometry['dry_mass_kg'], axis=0) / geometry['area_m2']
        gate_column = np.sum(maps[f'{suffix}_qsn_gated'].astype(np.float64) * geometry['dry_mass_kg'], axis=0) / geometry['area_m2']
        equal_column = np.sum(equal_qsnow.astype(np.float64) * geometry['dry_mass_kg'], axis=0) / geometry['area_m2']
        expected_columns = {
            f'{suffix}_source_qsn_column_kg_m2': source_column,
            f'{suffix}_gate_qsn_column_kg_m2': gate_column,
            f'{suffix}_eq_qsn_column_kg_m2': equal_column,
            f'{suffix}_gate_added_qsn_column_kg_m2': gate_column - source_column,
            f'{suffix}_eq_added_qsn_column_kg_m2': equal_column - source_column,
        }
        if any(not np.array_equal(maps[name], values) for name, values in expected_columns.items()):
            raise ValueError(f'{suffix}: diagnostic dry-mass column arrays differ from source QSNOW')
    if set(maps) != expected_map_keys or not np.array_equal(maps['proxy'], proxy):
        raise ValueError('frozen map key set or precip proxy differs from ORIGINAL input')
    expected_cases = common['case_records']
    field_cases = common.get('case_field_value_sha256', {})
    source_fields = common.get('source_field_value_sha256', {})
    if set(field_cases) != set(CASE_IDS) or set(source_fields) != {'ORIGINAL', 'B1'}:
        raise ValueError('native field value hash inventories are incomplete')
    if any(len(source_fields[family]) != 208 for family in source_fields):
        raise ValueError('source native field value inventory does not contain 208 variables')
    records = [helper_record, map_record, manifest_record,
               identity(ORIGINAL_INPUT_PATH), identity(B1_INPUT_PATH)]
    for case in CASE_IDS:
        row = expected_cases[case]
        audit = row.get('qsnow_audit', {})
        if common.get('case_qsnow_audit', {}).get(case) != audit:
            raise ValueError(f'{case}: top-level and case-local QSNOW audit records differ')
        input_family = 'B1' if case == 'ORIGINAL_B1_100' else 'ORIGINAL'
        exe_family = 'B1' if case == 'FIXED_ORIGINAL_100' else 'ORIGINAL'
        changes = ['QSNOW'] if case.startswith(('GATE_', 'EQ_')) else []
        if (row.get('input_family') != input_family or row.get('executable_family') != exe_family
            or audit.get('source_family') != input_family or audit.get('executable_family') != exe_family
            or audit.get('source_wrfinput_sha256') != (B1_INPUT_SHA256 if input_family == 'B1' else ORIGINAL_INPUT_SHA256)
            or audit.get('source_qsnow_value_sha256') != source_fields[input_family]['QSNOW']
            or audit.get('changed_variables') != changes
            or audit.get('other_207_values_unchanged') is not True
            or audit.get('all_metadata_unchanged') is not True):
            raise ValueError(f'{case}: native QSNOW-only and crossed input/executable audit mismatch')
        run_dir = Path(row['scratch_directory'])
        input_path = run_dir / 'wrfinput_d01'
        with netCDF4.Dataset(input_path) as staged:
            actual_fields = {name: native_value_hash(variable) for name, variable in staged.variables.items()}
            staged_qsnow = np.asarray(staged.variables['QSNOW'][0])
        expected_source_fields = source_fields[input_family]
        expected_case_fields = field_cases[case]
        if (len(actual_fields) != 208 or len(expected_case_fields) != 208
            or actual_fields != expected_case_fields
            or actual_fields['QSNOW'] != audit.get('scaled_qsnow_value_sha256')
            or any(actual_fields[name] != expected_source_fields[name]
                   for name in expected_source_fields if name != 'QSNOW')):
            raise ValueError(f'{case}: staged native field values do not match the source audit')
        if changes:
            pair = case.removeprefix('GATE_').removeprefix('EQ_')
            gate_name = 'G' + pair.removeprefix('G')
            key = f'{gate_name}_qsn_gated' if case.startswith('GATE_') else f'{gate_name}_qsn_equal_mass'
            if (not np.array_equal(staged_qsnow, maps[key])
                or audit.get('frozen_map_sha256') != map_record['sha256']
                or audit.get('frozen_gate_manifest_sha256') != manifest_record['sha256']):
                raise ValueError(f'{case}: staged QSNOW differs from frozen horizontal alpha map application')
            expected_alpha = maps[f'{gate_name}_alpha' if case.startswith('GATE_')
                                  else f'{gate_name}_alpha_equal_mass']
            expected_alpha_mean = float(np.mean(expected_alpha, dtype=np.float64))
            if (row.get('alpha') != expected_alpha_mean
                or audit.get('input_alpha_mean') != expected_alpha_mean):
                raise ValueError(f'{case}: recorded alpha identity differs from its frozen 2-D map')
            relative_error = float(audit.get('matched_gate_relative_mass_difference', -1.0))
            staged_mass = gate_helper.dry_snow_mass(staged_qsnow, geometry['dry_mass_kg'])
            if audit.get('staged_diagnostic_snow_mass_kg') != staged_mass:
                raise ValueError(f'{case}: reported staged dry-mass QSNOW total is inconsistent')
            if case.startswith('EQ_'):
                gate_name_suffix = case.removeprefix('EQ_')
                expected_relative = manifest['gate_controls'][gate_name_suffix]['relative_mass_difference']
                if (relative_error < 0 or relative_error > 1e-6
                    or audit.get('relative_mass_difference') != expected_relative
                    or relative_error != expected_relative):
                    raise ValueError(f'{case}: reported initial QSNOW mass matching exceeds or differs from the frozen audit')
        elif not np.array_equal(staged_qsnow, b1_qsnow if input_family == 'B1' else source_qsnow):
            raise ValueError(f'{case}: crossed case changed QSNOW unexpectedly')
        records.append(identity(input_path))
    if identity(helper_path) != helper_record:
        raise ValueError('gate helper source changed during native audit')
    return records


def check_selection_plan(path: Path = PLAN_PATH, expected_sha256: str = PLAN_SHA256):
    record = identity(path)
    if record['sha256'] != expected_sha256:
        raise ValueError('frozen weak/strong selection plan hash mismatch')
    plan = json.loads(Path(path).read_text(encoding='utf-8'))
    expected_cases = list(CASE_IDS)
    if (plan.get('status') != 'FROZEN_BEFORE_NEW_FORECAST_OUTPUTS'
        or plan.get('forecast_output_or_observation_used_for_gate') is not False
        or [row.get('case') for row in plan.get('experiment', {}).get('cases', [])] != expected_cases
        or plan.get('evaluation', {}).get('baseline') != 'ORIGINAL alpha=1.0 existing native history'
        or plan.get('evaluation', {}).get('leads_hours') != list(range(1, 7))
        or plan.get('evaluation', {}).get('thresholds_mm') != list(THRESHOLDS)
        or plan.get('evaluation', {}).get('paired_points_per_hour') != POINTS
        or plan.get('evaluation', {}).get('eligible_new_cases') !=
        'all eight completed identity-validated cases; crossed executable/input cases remain diagnostics and no single-process physical attribution is inferred'
        or plan.get('evaluation', {}).get('known_context_only_references') !=
        ['CONTROL_SNOW_300', 'IMPROVED_BG_FIXED', 'IMPROVED_SNOW_080']):
        raise ValueError('frozen weak/strong plan contract mismatch')
    selection = plan.get('evaluation', {})
    if ('18 CSI cells' not in selection.get('weak_qualification_cells', '')
        or 'strictly greater' not in selection.get('strong_qualification_cell', '')
        or 'NO_QUALIFIED_CANDIDATE' not in selection.get('candidate_admission', '')
        or 'No averages across thresholds, leads, or experiments' != selection.get('no_averaging')):
        raise ValueError('frozen admission or aggregation contract mismatch')
    if selection.get('ranking_order_after_admission') != [
        'descending lead-1 CSI at 10 mm', 'descending lead-1 CSI at 5 mm',
        'ascending lead-1 FAR at 10 mm', 'ascending lead-1 RMSE', 'ascending case ID']:
        raise ValueError('frozen candidate ranking contract mismatch')
    expected_parents = {
        'original_executable_sha256': ORIGINAL_EXECUTABLE_SHA256,
        'fixed_executable_sha256': FIXED_EXECUTABLE_SHA256,
        'original_wrfinput_sha256': ORIGINAL_INPUT_SHA256,
        'b1_wrfinput_sha256': B1_INPUT_SHA256,
        'common_wrfbdy_sha256': BOUNDARY_SHA256,
        'common_namelist_input_sha256': NAMELIST_SHA256,
    }
    if plan.get('parents') != {**plan.get('parents', {}), **expected_parents}:
        raise ValueError('frozen parent executable/input identity pins changed')
    if (selection.get('reference_score_archives', {}).get('analysis_receipt', {}).get('sha256') != PRIOR_RECEIPT_SHA256
        or list(selection.get('expected_contexts', {})) != list(CASE_IDS)):
        raise ValueError('frozen source archive or case context pins changed')
    archive_pins = selection['reference_score_archives']
    if (archive_pins.get('categorical_scores', {}).get('sha256') != PRIOR_CATEGORICAL_SHA256
        or archive_pins.get('continuous_scores', {}).get('sha256') != PRIOR_CONTINUOUS_SHA256):
        raise ValueError('frozen reference score CSV pins changed')
    return record, plan


def load_prior_arrays(path: Path = PRIOR_ANALYSIS):
    if (sha256(PRIOR_TOOL) != PRIOR_TOOL_SHA256
        or sha256(PRIOR_EXTENSION) != PRIOR_EXTENSION_SHA256
        or sha256(PRIOR_SENSITIVITY) != PRIOR_SENSITIVITY_SHA256):
        raise ValueError('pinned prior-analysis scorer sources changed')
    path = Path(path)
    receipt_path = path / 'receipt.json'
    if sha256(receipt_path) != PRIOR_RECEIPT_SHA256:
        raise ValueError('sealed 39-context lower-factor receipt pin changed')
    receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
    expected_cases = ('ORIGINAL', 'CURRENT_HYDRO', 'IMPROVED_BG_FIXED',
                      *(f'{arm}_SNOW_{suffix}' for arm in ('CONTROL', 'IMPROVED')
                        for suffix in ('000', '025', '050', '060', '070', '075', '080', '090', '125',
                                       '150', '175', '200', '250', '300', '110', '120', '130', '140')))
    if (receipt.get('status') != 'COMPLETE' or tuple(receipt.get('cases', ())) != expected_cases
        or receipt.get('points_per_hour') != POINTS
        or receipt.get('hours_utc') != list(HOURS)):
        raise ValueError('sealed 39-context reference archive scope changed')
    outputs = receipt.get('analysis_outputs', {})
    for name, output_record in outputs.items():
        output_path = path / name
        if (not output_path.is_file() or output_path.stat().st_size != output_record.get('size_bytes')
            or sha256(output_path) != output_record.get('sha256')):
            raise ValueError(f'sealed reference analysis output changed: {name}')
    if (sha256(path / 'categorical_scores.csv') != PRIOR_CATEGORICAL_SHA256
        or sha256(path / 'continuous_scores.csv') != PRIOR_CONTINUOUS_SHA256):
        raise ValueError('sealed lower-factor reference score CSV pins changed')
    arrays, records = {}, [identity(receipt_path)]
    coordinates = None
    expected_keys = set(expected_cases) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
    for hour in HOURS:
        artifact = path / f'hour_{hour}_arrays.npz'
        with np.load(artifact, allow_pickle=False) as archive:
            values = {key: np.array(archive[key]) for key in archive.files}
        if set(values) != expected_keys or any(value.shape != (POINTS,) for value in values.values()):
            raise ValueError(f'{hour}: sealed reference archive key/shape contract mismatch')
        if any(not np.isfinite(value).all() for name, value in values.items() if name != 'flat_index_yx'):
            raise ValueError(f'{hour}: sealed reference archive contains nonfinite data')
        ids = values['flat_index_yx']
        if len(np.unique(ids)) != POINTS:
            raise ValueError(f'{hour}: sealed reference point keys are not unique')
        coord = tuple(values[name] for name in ('flat_index_yx', 'latitude', 'longitude'))
        if coordinates is None:
            coordinates = tuple(array.copy() for array in coord)
        elif any(not np.array_equal(left, right) for left, right in zip(coordinates, coord)):
            raise ValueError(f'{hour}: sealed reference point keys or coordinates changed')
        arrays[hour] = values
        records.append(identity(artifact))
    records.extend(identity(path / name) for name in
                    ('categorical_scores.csv', 'continuous_scores.csv'))
    return None, arrays, records


def check_runtime(runtime_dir: Path, plan_record: dict):
    """Validate the frozen eight-case staging and post-run history receipts."""
    runtime_dir = Path(runtime_dir)
    common_path = runtime_dir / 'common_plan.json'
    common_record = identity(common_path)
    if common_record['sha256'] != COMMON_PLAN_SHA256:
        raise ValueError('frozen weak/strong runtime common-plan pin mismatch')
    common = json.loads(common_path.read_text(encoding='utf-8'))
    if (common.get('status') != 'PASS_READY_TO_LAUNCH'
        or common.get('selection_plan_sha256') != plan_record['sha256']
        or common.get('case_count') != len(CASE_IDS)
        or common.get('mpi_ranks_per_case') != 8 or common.get('omp_threads_per_rank') != 1
        or common.get('max_concurrent_cases') != 8
        or common.get('declared_input_count_per_case') != 89
        or set(common.get('case_records', {})) != set(CASE_IDS)):
        raise ValueError('weak/strong runtime common plan has incomplete scope or wrong selection pin')
    intel = common.get('intel_runtime', {})
    expected_profile = Path(intel.get('profile_path', ''))
    mpi_path = Path(intel.get('mpi_path', ''))
    mpi_env_path = Path(intel.get('mpi_env_path', ''))
    intel_records = [identity(expected_profile), identity(mpi_path), identity(mpi_env_path)]
    if (intel.get('profile_sha256') != INTEL_PROFILE_SHA256
        or intel_records[0]['sha256'] != INTEL_PROFILE_SHA256
        or intel.get('mpi_version') != INTEL_MPI_VERSION
        or intel_records[1]['sha256'] != intel.get('mpi_sha256')
        or intel_records[2]['sha256'] != intel.get('mpi_env_sha256')):
        raise ValueError('pinned Intel runtime profile or MPI identity mismatch')
    expected_history_names = list(HISTORY_NAMES)
    launch_scripts = common.get('launch_scripts_sha256')
    if not isinstance(launch_scripts, dict) or not launch_scripts:
        raise ValueError('weak/strong launch script pins are missing')
    records = [common_record, *intel_records]
    launch_records = []
    for name, expected in launch_scripts.items():
        record = identity(runtime_dir / name)
        if record['sha256'] != expected:
            raise ValueError(f'weak/strong launch script changed: {name}')
        launch_records.append(record)
    records.extend(launch_records)
    runs, case_receipts = {}, {}
    base_plan = json.loads((ROOT / 'docs/evidence/snow_lower_20261030/runtime/common_plan.json').read_text())
    base_record = identity(PRIOR_COMMON_PLAN)
    if base_record['sha256'] != PRIOR_COMMON_PLAN_SHA256:
        raise ValueError('pinned parent runtime input inventories changed')
    records.append(base_record)
    original_inventory = base_plan['original_source_sha256_before']
    b1_inventory = base_plan['source_b1_input_sha256_before']
    if len(original_inventory) != 89 or len(b1_inventory) != 89:
        raise ValueError('pinned parent input inventory is incomplete')
    if (common.get('source_plan_sha256') != PRIOR_COMMON_PLAN_SHA256
        or common.get('source_original_input_manifest_sha256') != original_inventory
        or common.get('source_b1_input_manifest_sha256') != b1_inventory
        or common.get('source_original_input_sha256') != ORIGINAL_INPUT_SHA256
        or common.get('source_b1_input_sha256') != B1_INPUT_SHA256
        or common.get('source_original_executable_sha256') != ORIGINAL_EXECUTABLE_SHA256
        or common.get('source_fixed_executable_sha256') != FIXED_EXECUTABLE_SHA256
        or common.get('common_boundary_sha256') != BOUNDARY_SHA256
        or common.get('common_namelist_sha256') != NAMELIST_SHA256
        or common.get('native_variable_count') != 208
        or common.get('other_207_values_unchanged') is not True
        or common.get('all_native_metadata_unchanged') is not True
        or common.get('source_inputs_before_after_equal') is not True):
        raise ValueError('weak/strong source inventories or native input audit summary changed')
    input_audit_records = audit_native_inputs(common, runtime_dir)
    records.extend(input_audit_records)
    for case in CASE_IDS:
        row = common['case_records'][case]
        staged = row.get('staged_sha256', {})
        run_dir = Path(row.get('scratch_directory', ''))
        receipt_path = runtime_dir / 'cases' / case / 'receipt.json'
        receipt_record = identity(receipt_path)
        receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
        expected_exe = (FIXED_EXECUTABLE_SHA256 if case == 'FIXED_ORIGINAL_100'
                        else ORIGINAL_EXECUTABLE_SHA256)
        expected_input = (B1_INPUT_SHA256 if case == 'ORIGINAL_B1_100'
                          else ORIGINAL_INPUT_SHA256)
        expected_base = b1_inventory
        expected_staged = dict(expected_base)
        expected_staged['wrf.exe'] = expected_exe
        if case.startswith(('GATE_', 'EQ_')):
            expected_staged['wrfinput_d01'] = staged.get('wrfinput_d01')
        else:
            expected_staged['wrfinput_d01'] = expected_input
        expected_staged['namelist.input'] = NAMELIST_SHA256
        expected_staged['wrfbdy_d01'] = BOUNDARY_SHA256
        if (row.get('case') != case or set(staged) != set(expected_staged)
            or any(staged.get(name) != value for name, value in expected_staged.items())
            or str(run_dir) != row.get('scratch_directory')
            or row.get('expected_hours') != expected_history_names):
            raise ValueError(f'{case}: staged input manifest or executable/input identity mismatch')
        if {name: sha256(run_dir / name) for name in staged} != staged:
            raise ValueError(f'{case}: staged runtime input hashes changed')
        if (receipt.get('status') != 'SUCCESS' or receipt.get('case') != case
            or receipt.get('selection_plan_sha256') != plan_record['sha256']
            or receipt.get('common_plan_sha256') != common_record['sha256']
            or receipt.get('scratch_directory') != str(run_dir)
            or receipt.get('staged_inputs_unchanged') is not True
            or receipt.get('source_unchanged') is not True
            or receipt.get('histories') != expected_history_names
            or set(receipt.get('output_sha256', {})) != set(expected_history_names)):
            raise ValueError(f'{case}: runtime receipt does not match frozen run contract')
        for name in expected_history_names:
            if sha256(run_dir / name) != receipt['output_sha256'][name]:
                raise ValueError(f'{case}/{name}: forecast history hash mismatch')
            records.append(identity(run_dir / name))
        records.extend(identity(run_dir / name) for name in staged)
        records.append(receipt_record)
        case_receipts[case] = receipt_record
        runs[case] = run_dir
    batch_path = runtime_dir / 'batch_receipt.json'
    history_path = runtime_dir / 'history_validation.json'
    final_path = runtime_dir / 'final_receipt.json'
    batch_record, history_record, final_record = identity(batch_path), identity(history_path), identity(final_path)
    batch = json.loads(batch_path.read_text(encoding='utf-8'))
    history = json.loads(history_path.read_text(encoding='utf-8'))
    final = json.loads(final_path.read_text(encoding='utf-8'))
    batch_case_ids = {row.get('case') for slot in batch.get('slots', []) for row in slot.get('cases', [])}
    batch_cases = [row for slot in batch.get('slots', []) for row in slot.get('cases', [])]
    if (batch.get('status') != 'SUCCESS' or batch.get('case_count') != len(CASE_IDS)
        or batch.get('common_plan_sha256') != common_record['sha256']
        or batch.get('selection_plan_sha256') != plan_record['sha256']
        or batch.get('common_plan_unchanged_after_batch') is not True
        or batch_case_ids != set(CASE_IDS)
        or any(row.get('runner_exit') != 0 or row.get('receipt_status') != 'SUCCESS'
               for row in batch_cases)
        or history.get('status') != 'SUCCESS' or set(history.get('cases', {})) != set(CASE_IDS)
        or final.get('status') != 'SUCCESS' or final.get('case_count') != len(CASE_IDS)
        or final.get('selection_plan_sha256') != plan_record['sha256']
        or final.get('common_plan_sha256') != common_record['sha256']
        or final.get('batch_receipt_sha256') != batch_record['sha256']
        or final.get('history_validation_sha256') != history_record['sha256']
        or final.get('all_case_histories_validated') is not True
        or set(final.get('cases', {})) != set(CASE_IDS)):
        raise ValueError('final batch/history validation receipts are incomplete or cross-unbound')
    for case in CASE_IDS:
        history_case = history['cases'][case]
        final_case = final['cases'][case]
        receipt = json.loads((runtime_dir / 'cases' / case / 'receipt.json').read_text(encoding='utf-8'))
        if (history_case.get('status') != 'PASS'
            or [row.get('file') for row in history_case.get('histories', [])] != list(HISTORY_NAMES)
            or final_case.get('status') != 'SUCCESS'
            or final_case.get('history_count') != len(HISTORY_NAMES)
            or final_case.get('history_sha256') != receipt.get('output_sha256')
            or final_case.get('receipt_sha256') != case_receipts[case]['sha256']):
            raise ValueError(f'{case}: final case history-validation binding failed')
        for row in history_case['histories']:
            if row.get('sha256') != receipt['output_sha256'].get(row['file']):
                raise ValueError(f"{case}/{row['file']}: history validation hash mismatch")
    records.extend((batch_record, history_record, final_record))
    return common, runs, records, case_receipts, common_record


def canonical_paired_arrays(base_arrays: dict):
    """Keep only frozen cases and shared verification coordinates in saved arrays."""
    names = set(CONTEXT_IDS) | {'reference', 'latitude', 'longitude', 'flat_index_yx'}
    return {hour: {name: np.array(value, copy=True) for name, value in base_arrays[hour].items()
                   if name in names}
            for hour in HOURS}


def build_candidate_arrays(run_dirs: dict, base_arrays: dict):
    """Remap forecast accumulations onto the sealed ORIGINAL 3,688-point cohort."""
    prior = load_module('pinned_snow_sensitivity', PRIOR_SENSITIVITY)
    scorer_module = prior.load_prior_scorer()
    scorer = scorer_module.load_scorer()
    inventory, mask, lat, lon, _ = scorer.evaluator.load_reference(
        prior.DEFAULT_REFERENCE_DIR, prior.DEFAULT_ANALYSIS_DIR)
    first = base_arrays[HOURS[0]]
    if (int(mask.sum()) != POINTS
        or not np.array_equal(np.flatnonzero(mask), first['flat_index_yx'])
        or not np.array_equal(lat[mask], first['latitude'])
        or not np.array_equal(lon[mask], first['longitude'])):
        raise ValueError('sealed paired arrays differ from the pinned RN1 reference cohort')
    evaluator = scorer.evaluator
    snapshots_by_case, histories, source_lat, source_lon = {}, [], None, None
    initial = datetime(2026, 8, 16, 12, tzinfo=timezone.utc)
    for case in CASE_IDS:
        snapshots = {}
        for hour, name in zip(range(12, 19), HISTORY_NAMES):
            path = run_dirs[case] / name
            before = identity(path)
            snapshot = evaluator.read_wrf_snapshot(path, initial + timedelta(hours=hour - 12), inventory)
            if identity(path) != before:
                raise ValueError(f'{path}: forecast changed during scoring')
            histories.append(before)
            if source_lat is None:
                source_lat, source_lon = snapshot['lat'], snapshot['lon']
            elif not np.array_equal(source_lat, snapshot['lat']) or not np.array_equal(source_lon, snapshot['lon']):
                raise ValueError(f'{case}: forecast grid differs from its peers')
            snapshots[hour] = snapshot
        snapshots_by_case[case] = snapshots
    evaluator.CASES = CASE_IDS
    reset_report = evaluator.check_resets(snapshots_by_case)
    x0, x1 = inventory['grid']['crop_x_inclusive']
    y0, y1 = inventory['grid']['crop_y_inclusive']
    ys, xs = slice(y0 - 2, y1), slice(x0 - 2, x1)
    mapping = evaluator.build_curvilinear_mapping(source_lat[ys, xs], source_lon[ys, xs], lat, lon, mask)
    output = canonical_paired_arrays(base_arrays)
    for case, snapshots in snapshots_by_case.items():
        cumulative = {}
        for hour, snapshot in snapshots.items():
            total, valid = evaluator.raw_total(snapshot)
            cumulative[hour] = evaluator.remap_field(total[ys, xs], valid[ys, xs], mapping)
        for hour in HOURS:
            values = output[hour]
            if (int((mask & mapping['valid']).sum()) != POINTS
                or not np.array_equal(np.flatnonzero(mask & mapping['valid']), values['flat_index_yx'])):
                raise ValueError(f'{case}/{hour}: remapping changed the paired point keys')
            paired = values['flat_index_yx']
            valid_pair = mask & mapping['valid'] & cumulative[hour - 1][1] & cumulative[hour][1]
            if int(valid_pair.sum()) != POINTS or not np.array_equal(np.flatnonzero(valid_pair), paired):
                raise ValueError(f'{case}/{hour}: forecast does not cover every paired point')
            diff = cumulative[hour][0] - cumulative[hour - 1][0]
            if np.any(diff[valid_pair] < -evaluator.NEGATIVE_TOLERANCE_MM):
                raise ValueError(f'{case}/{hour}: negative hourly precipitation accumulation')
            values[case] = np.maximum(diff[valid_pair], 0.0)
    return output, scorer, histories, mapping, reset_report


def score_arrays(arrays, scorer):
    categorical, continuous, transitions = [], [], []
    transition_arrays = {}
    for hour in HOURS:
        values = arrays[hour]
        obs = np.asarray(values['reference'], dtype=np.float64)
        if obs.shape != (POINTS,) or not np.isfinite(obs).all():
            raise ValueError(f'{hour}: reference does not contain {POINTS} finite paired values')
        lead = hour - 12
        when = {'lead_hour': lead, 'valid_utc': f'2026-08-16T{hour:02d}:00:00Z',
                'window_start_utc': f'2026-08-16T{hour - 1:02d}:00:00Z',
                'window_end_utc': f'2026-08-16T{hour:02d}:00:00Z'}
        for case in CONTEXT_IDS:
            prediction = np.asarray(values[case], dtype=np.float64)
            if prediction.shape != (POINTS,) or not np.isfinite(prediction).all():
                raise ValueError(f'{case}/{hour}: forecast is not 3688 finite points')
            error = prediction - obs
            continuous.append({**when, 'case': case, 'valid_obs': POINTS,
                               'mean_forecast_mm': float(np.mean(prediction)),
                               'mean_reference_mm': float(np.mean(obs)),
                               'MAE_mm': float(np.mean(np.abs(error))),
                               'RMSE_mm': float(np.sqrt(np.mean(error ** 2)))})
            for threshold in THRESHOLDS:
                categorical.append({**when, 'case': case, 'threshold_mm': threshold,
                                    'valid_obs': POINTS, **scorer.scores(prediction, obs, threshold)})
        original = np.asarray(values['ORIGINAL'], dtype=np.float64)
        hour_transition_arrays = {}
        for case in CONTEXT_IDS:
            if case == 'ORIGINAL':
                continue
            forecast = np.asarray(values[case], dtype=np.float64)
            for threshold in THRESHOLDS:
                obs_event = obs >= threshold
                old_event, new_event = original >= threshold, forecast >= threshold
                masks = {
                    'hit_gained': obs_event & ~old_event & new_event,
                    'hit_lost': obs_event & old_event & ~new_event,
                    'new_false_alarm': ~obs_event & ~old_event & new_event,
                    'false_alarm_removed': ~obs_event & old_event & ~new_event,
                }
                for kind, mask_values in masks.items():
                    hour_transition_arrays[f'{case}__t{threshold:g}__{kind}'] = mask_values.astype(np.uint8)
                transitions.append({'lead_hour': lead, 'case': case,
                                    'baseline_case': 'ORIGINAL', 'threshold_mm': threshold,
                                    **{kind: int(np.count_nonzero(mask_values))
                                       for kind, mask_values in masks.items()}})
        transition_arrays[hour] = hour_transition_arrays
    return categorical, continuous, transitions, transition_arrays


def _csi_counts(row):
    return int(row['hit']), int(row['miss']), int(row['false_alarm'])


def csi_ge_exact(candidate: dict, baseline: dict) -> bool:
    """Compare CSI ratios through integer contingency counts, without float tolerance."""
    ch, cm, cf = _csi_counts(candidate)
    bh, bm, bf = _csi_counts(baseline)
    candidate_denominator, baseline_denominator = ch + cm + cf, bh + bm + bf
    if candidate_denominator == 0 or baseline_denominator == 0:
        return False
    return ch * baseline_denominator >= bh * candidate_denominator


def csi_gt_exact(candidate: dict, baseline: dict) -> bool:
    ch, cm, cf = _csi_counts(candidate)
    bh, bm, bf = _csi_counts(baseline)
    candidate_denominator, baseline_denominator = ch + cm + cf, bh + bm + bf
    if candidate_denominator == 0 or baseline_denominator == 0:
        return False
    return ch * baseline_denominator > bh * candidate_denominator


def admission_rows(categorical):
    categories = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                  for row in categorical}
    constraints, candidates = [], []
    for case in CASE_IDS:
        candidate_rows = []
        for lead in range(1, 7):
            for threshold in WEAK_THRESHOLDS:
                candidate = categories[(case, lead, threshold)]
                baseline = categories[('ORIGINAL', lead, threshold)]
                passed = csi_ge_exact(candidate, baseline)
                constraints.append({'case': case, 'constraint': 'weak_CSI_at_least_ORIGINAL',
                                    'lead_hour': lead, 'threshold_mm': threshold,
                                    'candidate_hit': candidate['hit'], 'candidate_miss': candidate['miss'],
                                    'candidate_false_alarm': candidate['false_alarm'],
                                    'baseline_hit': baseline['hit'], 'baseline_miss': baseline['miss'],
                                    'baseline_false_alarm': baseline['false_alarm'],
                                    'status': 'PASS' if passed else 'FAIL'})
                candidate_rows.append(passed)
        candidate, baseline = categories[(case, 1, 10.0)], categories[('ORIGINAL', 1, 10.0)]
        strong = csi_gt_exact(candidate, baseline)
        constraints.append({'case': case, 'constraint': 'lead1_CSI10_strictly_greater_than_ORIGINAL',
                            'lead_hour': 1, 'threshold_mm': 10.0,
                            'candidate_hit': candidate['hit'], 'candidate_miss': candidate['miss'],
                            'candidate_false_alarm': candidate['false_alarm'],
                            'baseline_hit': baseline['hit'], 'baseline_miss': baseline['miss'],
                            'baseline_false_alarm': baseline['false_alarm'],
                            'status': 'PASS' if strong else 'FAIL'})
        candidates.append((case, all(candidate_rows) and strong))
    return constraints, candidates


def _finite_metric(value):
    return None if value is None or not math.isfinite(float(value)) else float(value)


def select_winner(categorical, continuous):
    constraints, admitted = admission_rows(categorical)
    category = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                for row in categorical}
    cont = {(row['case'], int(row['lead_hour'])): row for row in continuous}
    ranked = []
    for case, is_qualified in admitted:
        if not is_qualified:
            continue
        csi10 = _finite_metric(category[(case, 1, 10.0)]['CSI'])
        csi5 = _finite_metric(category[(case, 1, 5.0)]['CSI'])
        far10 = _finite_metric(category[(case, 1, 10.0)]['FAR'])
        rmse = _finite_metric(cont[(case, 1)]['RMSE_mm'])
        csi10_row, csi5_row, far10_row = (category[(case, 1, 10.0)],
                                          category[(case, 1, 5.0)],
                                          category[(case, 1, 10.0)])
        csi10_denominator = int(csi10_row['hit']) + int(csi10_row['miss']) + int(csi10_row['false_alarm'])
        csi5_denominator = int(csi5_row['hit']) + int(csi5_row['miss']) + int(csi5_row['false_alarm'])
        far10_denominator = int(far10_row['hit']) + int(far10_row['false_alarm'])
        ranked.append({'case': case, 'lead1_CSI_at_10mm': csi10,
                       'lead1_CSI_at_5mm': csi5, 'lead1_FAR_at_10mm': far10,
                       'lead1_RMSE_mm': rmse,
                       '_rank_csi10': Fraction(int(csi10_row['hit']), csi10_denominator),
                       '_rank_csi5': Fraction(int(csi5_row['hit']), csi5_denominator),
                       '_rank_far10': Fraction(int(far10_row['false_alarm']), far10_denominator)})
    def rank_key(row):
        return (row['_rank_csi10'] is None,
                -row['_rank_csi10'] if row['_rank_csi10'] is not None else 0,
                row['_rank_csi5'] is None,
                -row['_rank_csi5'] if row['_rank_csi5'] is not None else 0,
                row['_rank_far10'] is None,
                row['_rank_far10'] if row['_rank_far10'] is not None else 0,
                row['lead1_RMSE_mm'] is None,
                row['lead1_RMSE_mm'] if row['lead1_RMSE_mm'] is not None else 0.0,
                row['case'])
    ranked.sort(key=rank_key)
    for rank, row in enumerate(ranked, 1):
        row['rank'] = rank
        for name in ('_rank_csi10', '_rank_csi5', '_rank_far10'):
            del row[name]
    winner = ranked[0]['case'] if ranked else None
    return constraints, ranked, {
        'status': 'QUALIFIED_CANDIDATE' if winner else 'NO_QUALIFIED_CANDIDATE',
        'selected_case': winner,
        'ranking_order': ['descending lead-1 CSI at 10 mm', 'descending lead-1 CSI at 5 mm',
                          'ascending lead-1 FAR at 10 mm', 'ascending lead-1 RMSE',
                          'ascending case ID'],
        'admission': 'all 18 weak cells CSI >= ORIGINAL and strict lead-1 CSI@10 > ORIGINAL; zero tolerance',
        'qualified_cases': [row['case'] for row in ranked],
        'eligible_cases': list(CASE_IDS),
        'comparison_baseline': 'ORIGINAL',
        'constraints': 'weak thresholds 0.1/0.5/1.0 mm at each lead 1-6, plus lead-1 10.0 mm CSI',
        'weak_threshold_interpretation': 'These CSI floors include hits at all observed intensities above each cutoff, including heavy-rain hits; they are not light-rain-only scores.',
        'averaging': 'No aggregation across thresholds, leads, or experiments.',
    }


def comparison_rows(categorical, continuous):
    category = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
                for row in categorical}
    cont = {(row['case'], int(row['lead_hour'])): row for row in continuous}
    gate_rows, factorial_rows = [], []
    categorical_metrics = ('CSI', 'FAR', 'POD', 'ETS', 'frequency_bias')
    factorial_count_metrics = ('hit', 'miss', 'false_alarm')
    continuous_metrics = ('MAE_mm', 'RMSE_mm', 'mean_forecast_mm', 'mean_reference_mm')
    for gate, equal in GATE_PAIRS:
        for lead in range(1, 7):
            for threshold in THRESHOLDS:
                a, b = category[(gate, lead, threshold)], category[(equal, lead, threshold)]
                row = {'gate_case': gate, 'equal_mass_case': equal,
                       'lead_hour': lead, 'threshold_mm': threshold,
                       'row_type': 'categorical', 'metric': 'contingency scores',
                       'unit': 'dimensionless'}
                for metric in categorical_metrics:
                    av, bv = _finite_metric(a[metric]), _finite_metric(b[metric])
                    row[f'{metric}_gate'] = av
                    row[f'{metric}_equal_mass'] = bv
                    row[f'delta_{metric}_gate_minus_equal_mass'] = None if av is None or bv is None else av - bv
                gate_rows.append(row)
            a, b = cont[(gate, lead)], cont[(equal, lead)]
            row = {'gate_case': gate, 'equal_mass_case': equal, 'lead_hour': lead,
                   'threshold_mm': '', 'row_type': 'continuous',
                   'metric': 'precipitation errors and means', 'unit': 'mm'}
            for metric in continuous_metrics:
                av, bv = _finite_metric(a[metric]), _finite_metric(b[metric])
                row[f'{metric}_gate'] = av
                row[f'{metric}_equal_mass'] = bv
                row[f'delta_{metric}_gate_minus_equal_mass'] = None if av is None or bv is None else av - bv
            gate_rows.append(row)
    factorial_high = 'IMPROVED_BG_FIXED'
    factorial = ('ORIGINAL', 'FIXED_ORIGINAL_100', 'ORIGINAL_B1_100', factorial_high)
    for lead in range(1, 7):
        for threshold in THRESHOLDS:
            values = {case: category[(case, lead, threshold)] for case in factorial}
            for metric in categorical_metrics:
                raw = {case: _finite_metric(row[metric]) for case, row in values.items()}
                effect = (None if any(value is None for value in raw.values()) else
                          raw[factorial_high] - raw['ORIGINAL_B1_100']
                          - raw['FIXED_ORIGINAL_100'] + raw['ORIGINAL'])
                factorial_rows.append({'lead_hour': lead, 'threshold_mm': threshold,
                                       'metric': metric, 'original_old_exe': raw['ORIGINAL'],
                                       'original_fixed_exe': raw['FIXED_ORIGINAL_100'],
                                       'b1_original_exe': raw['ORIGINAL_B1_100'],
                                       'b1_fixed_exe': raw[factorial_high],
                                       'difference_in_differences': effect,
                                       'interpretation': '2x2 diagnostic interaction; no single-process physical attribution'})
            for metric in factorial_count_metrics:
                raw = {case: int(values[case][metric]) for case in factorial}
                effect = (raw[factorial_high] - raw['ORIGINAL_B1_100']
                          - raw['FIXED_ORIGINAL_100'] + raw['ORIGINAL'])
                factorial_rows.append({'lead_hour': lead, 'threshold_mm': threshold,
                                       'metric': metric, 'original_old_exe': raw['ORIGINAL'],
                                       'original_fixed_exe': raw['FIXED_ORIGINAL_100'],
                                       'b1_original_exe': raw['ORIGINAL_B1_100'],
                                       'b1_fixed_exe': raw[factorial_high],
                                       'difference_in_differences': effect,
                                       'interpretation': '2x2 diagnostic interaction in event counts; no physical attribution'})
        values = {case: cont[(case, lead)] for case in factorial}
        for metric in continuous_metrics:
            raw = {case: _finite_metric(row[metric]) for case, row in values.items()}
            effect = (None if any(value is None for value in raw.values()) else
                      raw[factorial_high] - raw['ORIGINAL_B1_100']
                      - raw['FIXED_ORIGINAL_100'] + raw['ORIGINAL'])
            factorial_rows.append({'lead_hour': lead, 'threshold_mm': '', 'metric': metric,
                                   'original_old_exe': raw['ORIGINAL'],
                                   'original_fixed_exe': raw['FIXED_ORIGINAL_100'],
                                   'b1_original_exe': raw['ORIGINAL_B1_100'],
                                   'b1_fixed_exe': raw[factorial_high],
                                   'difference_in_differences': effect,
                                   'interpretation': '2x2 diagnostic interaction; no single-process physical attribution'})
    return gate_rows, factorial_rows


def exact_csi_change_rows(categorical):
    """Show the exact hit/false-alarm numerator behind every CSI delta."""
    indexed = {(row['case'], int(row['lead_hour']), float(row['threshold_mm'])): row
               for row in categorical}
    rows = []
    for case in CONTEXT_IDS:
        if case == 'ORIGINAL':
            continue
        for lead in range(1, 7):
            for threshold in THRESHOLDS:
                baseline = indexed[('ORIGINAL', lead, threshold)]
                candidate = indexed[(case, lead, threshold)]
                baseline_obs = int(baseline['hit']) + int(baseline['miss'])
                candidate_obs = int(candidate['hit']) + int(candidate['miss'])
                if baseline_obs != candidate_obs:
                    raise ValueError(f'{case}/{lead}/{threshold}: verification event count changed')
                h0, f0 = int(baseline['hit']), int(baseline['false_alarm'])
                hc, fc = int(candidate['hit']), int(candidate['false_alarm'])
                d0 = h0 + int(baseline['miss']) + f0
                dc = hc + int(candidate['miss']) + fc
                defined = d0 > 0 and dc > 0
                numerator = hc * d0 - h0 * dc if defined else None
                factorized_numerator = ((baseline_obs + f0) * (hc - h0) - h0 * (fc - f0)
                                        if defined else None)
                denominator = d0 * dc if defined else None
                if numerator != factorized_numerator:
                    raise ValueError(f'{case}/{lead}/{threshold}: exact CSI algebra forms disagree')
                rows.append({'case': case, 'baseline_case': 'ORIGINAL', 'lead_hour': lead,
                             'threshold_mm': threshold, 'observed_event_count': baseline_obs,
                             'baseline_hit': h0, 'candidate_hit': hc,
                             'hit_delta_candidate_minus_baseline': hc - h0,
                             'baseline_miss': int(baseline['miss']),
                             'candidate_miss': int(candidate['miss']),
                             'miss_delta_candidate_minus_baseline': int(candidate['miss']) - int(baseline['miss']),
                             'baseline_false_alarm': f0, 'candidate_false_alarm': fc,
                             'false_alarm_delta_candidate_minus_baseline': fc - f0,
                             'baseline_CSI_denominator': d0, 'candidate_CSI_denominator': dc,
                             'csi_delta_exact_numerator': numerator,
                             'csi_delta_factorized_numerator': factorized_numerator,
                             'csi_delta_exact_denominator': denominator,
                             'csi_delta_sign': ('UNDEFINED' if not defined else 'POSITIVE' if numerator > 0
                                                else 'NEGATIVE' if numerator < 0 else 'ZERO'),
                             'interpretation': 'Exact contingency-count CSI algebra; descriptive, not causal.'})
    return rows


def point_differences(arrays):
    output = {}
    for hour in HOURS:
        values = arrays[hour]
        baseline = np.asarray(values['ORIGINAL'], dtype=np.float64)
        arrays_out = {name: np.asarray(values[name]) for name in
                      ('reference', 'flat_index_yx', 'latitude', 'longitude')}
        for case in CONTEXT_IDS:
            arrays_out[case] = np.asarray(values[case], dtype=np.float64) - baseline
        if not np.array_equal(arrays_out['ORIGINAL'], np.zeros(POINTS, dtype=np.float64)):
            raise ValueError(f'{hour}: ORIGINAL difference from itself is not exactly zero')
        output[hour] = arrays_out
    return output


def case_metadata(common):
    records = {}
    for case in CASE_IDS:
        runtime = common['case_records'][case]
        audit = runtime['qsnow_audit']
        row = {
            'role': 'eligible_new_case',
            'transform': audit['transform'],
            'input_family': runtime['input_family'],
            'executable_family': runtime['executable_family'],
            'executable_sha256': runtime['staged_sha256']['wrf.exe'],
            'source_wrfinput_sha256': audit['source_wrfinput_sha256'],
            'staged_wrfinput_sha256': runtime['staged_sha256']['wrfinput_d01'],
            'changed_native_variables': audit['changed_variables'],
            'staged_diagnostic_snow_mass_kg': audit['staged_diagnostic_snow_mass_kg'],
        }
        if case.startswith('GATE_'):
            row.update({
                'alpha_kind': '2-D horizontal gate field applied at every mass level',
                'alpha_min': audit['gate_alpha_min'],
                'alpha_max': audit['gate_alpha_max'],
                'alpha_horizontal_mean': audit['gate_alpha_mean'],
                'uniform_alpha': None,
                'matched_gate_relative_mass_difference': None,
            })
        elif case.startswith('EQ_'):
            row.update({
                'alpha_kind': 'uniform 2-D field matched to paired gate diagnostic snow mass',
                'alpha_min': audit['equal_mass_alpha'],
                'alpha_max': audit['equal_mass_alpha'],
                'alpha_horizontal_mean': audit['equal_mass_alpha'],
                'uniform_alpha': audit['equal_mass_alpha'],
                'matched_gate_relative_mass_difference': audit['matched_gate_relative_mass_difference'],
            })
        else:
            row.update({'alpha_kind': 'unchanged QSNOW input', 'alpha_min': 1.0,
                        'alpha_max': 1.0, 'alpha_horizontal_mean': 1.0,
                        'uniform_alpha': 1.0, 'matched_gate_relative_mass_difference': None})
        records[case] = row
    return records


def intensity_band_rows(arrays):
    """Count point transitions inside disjoint observation and forecast intensity bands."""
    transition_rows, histogram_rows = [], []
    for hour in HOURS:
        lead = hour - 12
        values = arrays[hour]
        observed = np.asarray(values['reference'], dtype=np.float64)
        original = np.asarray(values['ORIGINAL'], dtype=np.float64)
        for case in CONTEXT_IDS:
            if case == 'ORIGINAL':
                continue
            candidate = np.asarray(values[case], dtype=np.float64)
            for obs_name, lower, upper in INTENSITY_BINS:
                obs_mask = observed >= lower
                if upper is not None:
                    obs_mask &= observed < upper
                obs_event_count = int(np.count_nonzero(obs_mask))
                for threshold in THRESHOLDS:
                    obs_event = observed >= threshold
                    baseline_event, candidate_event = original >= threshold, candidate >= threshold
                    transition_rows.append({
                        'lead_hour': lead, 'case': case, 'baseline_case': 'ORIGINAL',
                        'threshold_mm': threshold, 'observed_bin': obs_name,
                        'observed_lower_mm': lower, 'observed_upper_mm': '' if upper is None else upper,
                        'point_count': obs_event_count,
                        'baseline_hits': int(np.count_nonzero(obs_mask & obs_event & baseline_event)),
                        'candidate_hits': int(np.count_nonzero(obs_mask & obs_event & candidate_event)),
                        'hit_gained': int(np.count_nonzero(obs_mask & obs_event & ~baseline_event & candidate_event)),
                        'hit_lost': int(np.count_nonzero(obs_mask & obs_event & baseline_event & ~candidate_event)),
                        'baseline_direct_event_misses': int(np.count_nonzero(obs_mask & obs_event & ~baseline_event)),
                        'candidate_direct_event_misses': int(np.count_nonzero(obs_mask & obs_event & ~candidate_event)),
                        'baseline_predicted_events': int(np.count_nonzero(obs_mask & baseline_event)),
                        'candidate_predicted_events': int(np.count_nonzero(obs_mask & candidate_event)),
                        'baseline_false_alarms': int(np.count_nonzero(obs_mask & ~obs_event & baseline_event)),
                        'candidate_false_alarms': int(np.count_nonzero(obs_mask & ~obs_event & candidate_event)),
                    })
                for forecast_case, forecast in (('ORIGINAL', original), (case, candidate)):
                    for forecast_name, pred_lower, pred_upper in INTENSITY_BINS:
                        predicted_bin = forecast >= pred_lower
                        if pred_upper is not None:
                            predicted_bin &= forecast < pred_upper
                        histogram_rows.append({
                            'lead_hour': lead, 'case': case, 'observed_bin': obs_name,
                            'forecast_case': forecast_case, 'forecast_bin': forecast_name,
                            'point_count': int(np.count_nonzero(obs_mask & predicted_bin)),
                        })
    return transition_rows, histogram_rows


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f'cannot write empty CSV: {path}')
    with Path(path).open('w', encoding='utf-8', newline='') as stream:
        fieldnames = list(dict.fromkeys(key for row in rows for key in row))
        for key in ('row_type', 'metric', 'unit'):
            if any(key in row for row in rows) and key not in fieldnames:
                fieldnames.insert(0, key)
        writer = csv.DictWriter(stream, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def score(runtime_dir: Path = RUNTIME_DIR, output: Path = EVIDENCE_DIR / 'analysis',
          plan_path: Path = PLAN_PATH, plan_sha256: str = PLAN_SHA256,
          prior_analysis: Path = PRIOR_ANALYSIS):
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError(f'refusing to replace existing analysis output: {output}')
    plan_record, plan = check_selection_plan(plan_path, plan_sha256)
    _, base, prior_records = load_prior_arrays(prior_analysis)
    common, run_dirs, runtime_records, case_receipts, common_record = check_runtime(runtime_dir, plan_record)
    combined, scorer, history_records, mapping, resets = build_candidate_arrays(run_dirs, base)
    categorical, continuous, transitions, transition_arrays = score_arrays(combined, scorer)
    admission, ranked, winner = select_winner(categorical, continuous)
    gate_rows, factorial_rows = comparison_rows(categorical, continuous)
    exact_delta_rows = exact_csi_change_rows(categorical)
    differences = point_differences(combined)
    band_transitions, band_histograms = intensity_band_rows(combined)
    normalized_prior_records = [identity(Path(record['path'])) for record in prior_records]
    all_inputs = [identity(Path(__file__)), plan_record, *normalized_prior_records,
                  identity(PRIOR_TOOL), identity(PRIOR_EXTENSION),
                  identity(PRIOR_SENSITIVITY), common_record,
                  *runtime_records, *history_records]
    all_inputs.sort(key=lambda row: (row['path'], row['sha256']))
    for record in all_inputs:
        if identity(Path(record['path'])) != record:
            raise ValueError(f"input changed during scoring: {record['path']}")
    output.mkdir(parents=True, exist_ok=False)
    try:
        for hour, values in combined.items():
            np.savez_compressed(output / f'hour_{hour}_arrays.npz', **values)
            np.savez_compressed(output / f'hour_{hour}_difference_vs_original.npz', **differences[hour])
            np.savez_compressed(output / f'hour_{hour}_transitions_vs_original.npz',
                                **transition_arrays[hour])
        write_csv(output / 'categorical_scores.csv', categorical)
        write_csv(output / 'continuous_scores.csv', continuous)
        write_csv(output / 'transitions_vs_original.csv', transitions)
        write_csv(output / 'admission_constraints.csv', admission)
        if ranked:
            write_csv(output / 'qualified_ranking.csv', ranked)
        write_csv(output / 'gate_equal_mass_comparison.csv', gate_rows)
        write_csv(output / 'factorial_difference_in_differences.csv', factorial_rows)
        write_csv(output / 'csi_change_exact_counts.csv', exact_delta_rows)
        write_csv(output / 'observation_band_transitions.csv', band_transitions)
        write_csv(output / 'observed_forecast_bin_counts.csv', band_histograms)
        (output / 'winner.json').write_text(json.dumps(winner, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        for record in all_inputs:
            if identity(Path(record['path'])) != record:
                raise ValueError(f"input changed during analysis: {record['path']}")
        artifacts = {path.name: {'sha256': sha256(path), 'size_bytes': path.stat().st_size}
                     for path in sorted(output.iterdir())}
        receipt = {
            'status': 'COMPLETE', 'plan': plan_record,
            'cases': list(CONTEXT_IDS), 'eligible_cases': list(CASE_IDS),
            'context_only_cases': ['CONTROL_SNOW_300', 'IMPROVED_BG_FIXED', 'IMPROVED_SNOW_080'],
            'hours_utc': list(HOURS), 'points_per_hour': POINTS, 'thresholds_mm': list(THRESHOLDS),
            'row_counts': {'categorical': len(categorical), 'continuous': len(continuous),
                           'transitions': len(transitions), 'admission_constraints': len(admission),
                           'gate_equal_mass_comparison': len(gate_rows),
                           'factorial_difference_in_differences': len(factorial_rows),
                           'csi_change_exact_counts': len(exact_delta_rows),
                           'observation_band_transitions': len(band_transitions),
                           'observed_forecast_bin_counts': len(band_histograms)},
            'winner': winner, 'ranking': ranked,
            'case_metadata': case_metadata(common),
            'comparison_baseline': 'ORIGINAL',
            'transition_scope': 'per-point flags and counts versus ORIGINAL at each lead and threshold',
            'pointwise_difference': 'hourly total precipitation minus ORIGINAL on same RN1 point keys',
            'observed_intensity_bins': {
                'edges_mm': [['dry', 0.0, 0.1], ['light', 0.1, 1.0], ['moderate', 1.0, 5.0],
                             ['strong', 5.0, 10.0], ['very_strong', 10.0, None]],
                'scope': 'diagnostic counts on all 3,688 paired verification points; no input gate or eligibility mask',
                'aggregation': 'point counts only; no means across bins, thresholds, leads, or cases'},
            'runtime_plan': common_record, 'runtime_case_receipts': case_receipts,
            'prior_analysis_receipt': identity(Path(prior_analysis) / 'receipt.json'),
            'mapping_residual_max_deg': mapping['residual_max_deg'], 'reset_checks': resets,
            'sources': all_inputs, 'analysis_outputs': artifacts,
            'interpretation_limits': plan['interpretation_limits'],
            'rmse_ranking_scope': 'lead-1 RMSE; frozen in the pre-output selection plan'}
        (output / 'receipt.json').write_text(
            json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + '\n', encoding='utf-8')
        return receipt
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-dir', type=Path, default=RUNTIME_DIR)
    parser.add_argument('--plan', type=Path, default=PLAN_PATH)
    parser.add_argument('--plan-sha256', default=PLAN_SHA256)
    parser.add_argument('--prior-analysis', type=Path, default=PRIOR_ANALYSIS)
    parser.add_argument('--output', type=Path, default=EVIDENCE_DIR / 'analysis')
    args = parser.parse_args()
    result = score(args.runtime_dir, args.output, args.plan, args.plan_sha256, args.prior_analysis)
    print(json.dumps({'status': result['status'], 'winner': result['winner']}, indent=2))


if __name__ == '__main__':
    main()
