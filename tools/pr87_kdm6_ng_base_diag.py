"""Add read-only diagnostics to the frozen PR87 nongraupel-base rejection."""
from __future__ import annotations

import hashlib


V11A_MODULE_SOURCE_SHA256 = "b14092c4664392804c99b6e068d04456f67c8205fefa1a0e8aaedb93825315e3"
V13_MODULE_SOURCE_SHA256 = "a3e6d94ee5030e020ecf4cded19c4a0e7aa1dcef96a4d32e37056fc2d4b7117e"
V14_MODULE_SOURCE_SHA256 = 'bfead795184a3647f8f362bf4fc820a865c0352fb44e6d8de9313b5df4469102'
V15_MODULE_SOURCE_SHA256 = 'e7b4225681cfce25c7096ceb196108ffe8d2e5ee2e4e309e0b890cd6093d1b20'
SUPPORTED_MODULE_SOURCE_SHA256 = frozenset({
    V11A_MODULE_SOURCE_SHA256,
    V13_MODULE_SOURCE_SHA256,
    V14_MODULE_SOURCE_SHA256,
    V15_MODULE_SOURCE_SHA256,
})
FATAL_GUARD = (
    "                if (.not.rain_ng_base_valid .or. rain_qv_before.lt.0.0 .or. &\n"
    "                    .not.ieee_is_finite(rain_qv_before)) &\n"
    "                  error stop 'KDM6 invalid base before nongraupel admission'\n"
)
DIAGNOSTIC = (
    "                if (.not.rain_ng_base_valid .or. rain_qv_before.lt.0.0 .or. &\n"
    "                    .not.ieee_is_finite(rain_qv_before)) then\n"
    "                  write(*,*) 'PR87_NG_BASE_FAIL_META',pr87_model_timestep,lat,i,k,loop,n, &\n"
    "                       rain_ng_search_status,rain_full_evap_pending(i,k),rain_ng_base_valid\n"
    "                  write(*,*) 'PR87_NG_BASE_FAIL_STATE',rain_q_fixed,rain_n_fixed, &\n"
    "                       rain_bg_fixed,rain_t_fixed,rain_qv_before,dry_carrier_density(i,k)\n"
    "                  write(*,'(a,12(1x,z8.8))') 'PR87_NG_BASE_FAIL_STATE_HEX', &\n"
    "                       transfer([rain_q_fixed,rain_n_fixed,rain_bg_fixed,rain_t_fixed, &\n"
    "                       rain_qv_before,dry_carrier_density(i,k)],[0],12)\n"
    "                  write(*,*) 'PR87_NG_BASE_FAIL_QPROC',rain_ng_q_process\n"
    "                  write(*,*) 'PR87_NG_BASE_FAIL_NPROC',rain_ng_n_process\n"
    "                  write(*,*) 'PR87_NG_BASE_FAIL_BGTVPROC',rain_ng_bg_process, &\n"
    "                       rain_ng_t_process,rain_ng_qv_process\n"
    "                  write(*,*) 'PR87_NG_BASE_FAIL_LIMITS',pidnr,qmin,ncmin,qcrmin,dmr, &\n"
    "                       lamdarmin,lamdarmax,100.0,900.0,pidnc,dmc,lamdacmin, &\n"
    "                       lamdacmax,pidni,dmi,lamdaimin,lamdaimax\n"
    "                  flush(6)\n"
    "                  error stop 'KDM6 invalid base before nongraupel admission'\n"
    "                endif\n"
)


def _sha256_text(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def generate_ng_base_diagnostic(source: str) -> str:
    """Add diagnostic writes immediately before the unchanged rejection."""
    actual = _sha256_text(source)
    if actual not in SUPPORTED_MODULE_SOURCE_SHA256:
        raise ValueError(
            f"KDM6 source identity mismatch: expected one of "
            f"{sorted(SUPPORTED_MODULE_SOURCE_SHA256)}, got {actual}"
        )
    count = source.count(FATAL_GUARD)
    if count != 1:
        raise ValueError(f"expected one nongraupel base rejection guard, found {count}")
    return source.replace(FATAL_GUARD, DIAGNOSTIC, 1)
