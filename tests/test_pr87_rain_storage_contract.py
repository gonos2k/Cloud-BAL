#!/usr/bin/env python3
"""Bind rain-storage transforms to the frozen native fragments and consumer."""
from __future__ import annotations

import hashlib
import gzip
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))

from pr87_rain_storage_contract import (  # noqa: E402
    V10_FRAGMENT_SHA256,
    extend_kdm6_public_return,
    extend_native_update,
)
from pr87_kdm6_ng_base_diag import DIAGNOSTIC, FATAL_GUARD  # noqa: E402

EVIDENCE = ROOT / 'docs/evidence'
V10_NATIVE = EVIDENCE / 'pr87_two_step_v10_20261016/native_update.f90.gz'
V12_KDM6 = EVIDENCE / 'pr87_two_step_v12diag_20261016/module_mp_kdm6.F.gz'
V13_NATIVE = EVIDENCE / 'pr87_two_step_v13_20261016/native_update.f90.gz'
V13_KDM6_DIAGNOSTIC = EVIDENCE / 'pr87_two_step_v13_20261016/module_mp_kdm6.F.gz'
V12_KDM6_SHA256 = '398d7f4cd1e7493a9eb5ea677167ee59a9e7f03074d91c89d9bc6342d12cf482'
V16_NATIVE = EVIDENCE / 'pr87_two_step_v16_20261016/native_update.f90.gz'
V16_NATIVE_SHA256 = '716d3958970edeedd61eacf938272e94393ba9177807ecdffdd8b934143b836b'
V13_NATIVE_SHA256 = '4a1175d2f4a007672ab5d47d95316237889661665f323d046a7ff71bfa333b01'
V13_KDM6_DIAGNOSTIC_SHA256 = 'f9652dc7208bb81edd57a23de53c58d3b23a531967ea46c0ec7aa510e0599a98'
V13_KDM6_PLAIN_SHA256 = 'a3e6d94ee5030e020ecf4cded19c4a0e7aa1dcef96a4d32e37056fc2d4b7117e'


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_native_storage_transform_matches_v16_artifact() -> None:
    source_bytes = gzip.decompress(V10_NATIVE.read_bytes())
    assert sha256(source_bytes) == V10_FRAGMENT_SHA256
    transformed = extend_native_update(source_bytes.decode())
    actual_bytes = gzip.decompress(V16_NATIVE.read_bytes())
    assert sha256(actual_bytes) == V16_NATIVE_SHA256
    assert transformed.encode() == actual_bytes
    assert 'strict_number_pair=3,volume_number_bounds=rain_bounds' in transformed
    assert 'volume_number_bounds=rain_bounds(c,:)' in transformed
    assert 'qa64(cell,p)=rate(1); na64(cell,p)=rate(2)' in transformed
    assert 'REAL(qa(cell,p),real64)' not in transformed


def test_public_return_matches_native_coefficients_and_records_storage() -> None:
    native = gzip.decompress(V13_NATIVE.read_bytes()).decode()
    diagnostic_bytes = gzip.decompress(V13_KDM6_DIAGNOSTIC.read_bytes())
    assert sha256(diagnostic_bytes) == V13_KDM6_DIAGNOSTIC_SHA256
    diagnostic_module = diagnostic_bytes.decode()
    assert diagnostic_module.count(DIAGNOSTIC) == 1
    module = diagnostic_module.replace(DIAGNOSTIC, FATAL_GUARD, 1)
    assert sha256(module.encode()) == V13_KDM6_PLAIN_SHA256

    # The grouped source and the KDM6 return guard must name the same source
    # coefficients. The wrapper passes those live values to the external store.
    native_coefficients = re.search(
        r'PARAMETER\s*::\s*rain_pidn=([0-9.]+)_real32\s*,\s*'
        r'rain_power=([0-9.]+)_real32\s*\n\s*'
        r'REAL\(real32\),PARAMETER\s*::\s*rain_lambda_min=([0-9.]+)_real32\s*,\s*'
        r'rain_lambda_max=([0-9.]+)_real32',
        native,
        re.I,
    )
    assert native_coefficients, 'native rain source coefficients are missing'
    native_values = tuple(float(value) for value in native_coefficients.groups())
    guard_values = re.search(
        r'if\s*\(pidnr\s*/=([0-9.]+)\s*\.or\.\s*dmr\s*/=([0-9.]+)\s*\.or\.\s*&\s*\n'
        r'\s*lamdarmin\s*/=([0-9.]+)\s*\.or\.\s*lamdarmax\s*/=([0-9.]+)\)',
        module,
        re.I,
    )
    assert guard_values, 'KDM6 native coefficient identity guard is missing'
    assert tuple(float(value) for value in guard_values.groups()) == native_values
    assert 'external :: pr87_rain_public_store' in module.lower()
    assert ('call pr87_rain_public_store(qrs(i,k,1),nrs(i,k,1),dry_density(i,k), &\n'
            '              pidnr,dmr,lamdarmin,lamdarmax,pr87_rain_q_public,pr87_rain_n_public, &\n'
            '              number_valid,pr87_rain_store_dq,pr87_rain_store_dn,pr87_rain_store_adjustment)') in module

    # Validate that the source transform itself still emits the exact handoff
    # and that the V13 module retains it among the other KDM6 overlays.
    v12_bytes = gzip.decompress(V12_KDM6.read_bytes())
    assert sha256(v12_bytes) == V12_KDM6_SHA256
    transformed_base = extend_kdm6_public_return(v12_bytes.decode())
    for fragment in (
        'external :: pr87_rain_public_store',
        "open(newunit=pr87_rain_store_unit,file='pr87_rain_public_store.raw'",
        "'PR87_RAIN_PUBLIC_STORE',itimestep,j,i,k,pr87_rain_store_adjustment, &",
        'pr87_rain_store_dn,pr87_rain_roundtrip_dn',
        'qr(i,k,j)=pr87_rain_q_public',
        'number_value=pr87_rain_n_public',
    ):
        assert fragment in transformed_base
        assert fragment in module

    call_position = module.index('call pr87_rain_public_store(')
    write_position = module.index("'PR87_RAIN_PUBLIC_STORE',", call_position)
    q_store_position = module.index('qr(i,k,j)=pr87_rain_q_public', call_position)
    n_store_position = module.index('number_value=pr87_rain_n_public', call_position)
    assert call_position < write_position < q_store_position < n_store_position


if __name__ == '__main__':
    test_native_storage_transform_matches_v16_artifact()
    test_public_return_matches_native_coefficients_and_records_storage()
    print('PR87 rain-storage transform tests PASS')
