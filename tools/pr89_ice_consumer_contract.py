"""Connect joint ICE storage to the pinned native KDM6 inactive-mass contract."""
from __future__ import annotations

import hashlib


V50_MODULE_EM_SHA256 = "4d07170e68699e62276eb3ec800c123b6993e91cdaa9aae2411b4909c34a14c0"
JOINT_TRANSPORT_SHA256 = "aef7f536f85983f4fcb9dd266fafc6c5e900dbf0e1c485b1afd55a8dee56bd51"
ICE_LIMIT_EXPRESSION = "REAL(NEAREST(1.e-14,-1.0),real64)"


def connect_ice_consumer(source: str, joint_transport_source: str) -> str:
    """Embed the tested shared transport module and connect host ICE gates."""
    digest = hashlib.sha256(source.encode()).hexdigest()
    if digest != V50_MODULE_EM_SHA256:
        raise ValueError(f"unexpected pinned V50 module_em_pr85.F hash: {digest}")
    transport_digest = hashlib.sha256(joint_transport_source.encode()).hexdigest()
    if transport_digest != JOINT_TRANSPORT_SHA256:
        raise ValueError(f"unexpected shared joint transport hash: {transport_digest}")
    if "inactive_mass_limits=" in source or "inactive_mass_limit=" in source:
        raise ValueError("PR89 ice consumer admission is already installed")
    module_start = "module cloud_bal_joint_transport\n"
    module_end = "end module cloud_bal_joint_transport\n"
    if not source.startswith(module_start) or source.count(module_end) != 1:
        raise ValueError("pinned embedded joint transport module is missing or ambiguous")
    start = source.index(module_start)
    end = source.index(module_end, start) + len(module_end)
    source = source[:start] + joint_transport_source.rstrip() + "\n\n" + source[end:]

    transformed = _replace_once(
        source,
        "strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.])",
        "strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.], &\n"
        f"                         inactive_mass_limits=[0.0_real64,{ICE_LIMIT_EXPRESSION}, &\n"
        "                         0.0_real64,0.0_real64])",
        "joint QNB update call",
    )
    main_start = transformed.index("SUBROUTINE rk_update_joint_moments(")
    main_end = transformed.index("CONTAINS\n", main_start)
    main = transformed[main_start:main_end]
    main = _replace_once(
        main,
        "strict_mass_ratio=(p==4))\n",
        "strict_mass_ratio=(p==4), &\n"
        f"             inactive_mass_limit=MERGE({ICE_LIMIT_EXPRESSION},0.0_real64,p==2))\n",
        "full candidate diagnostic",
    )
    main = _replace_once(
        main,
        "minmass(p),maxmass(p))\n        END IF\n        IF (.NOT.source_valid)",
        "minmass(p),maxmass(p),MERGE(" + ICE_LIMIT_EXPRESSION + ",0.0_real64,p==2))\n"
        "        END IF\n        IF (.NOT.source_valid)",
        "source candidate diagnostic",
    )
    transformed = transformed[:main_start] + main + transformed[main_end:]

    cert_start = "SUBROUTINE certify_graupel_storage("
    certifier = _procedure(transformed, cert_start, "END SUBROUTINE certify_graupel_storage")
    certifier = _replace_once(
        certifier,
        "allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)\n            END IF\n",
        "allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &\n"
        f"                  inactive_mass_limit={ICE_LIMIT_EXPRESSION})\n            END IF\n",
        "certifier pair-2 store gate",
    )
    transformed = _replace_procedure(
        transformed, cert_start, "END SUBROUTINE certify_graupel_storage", certifier
    )

    baseline_start = "SUBROUTINE find_failed_baseline_pairs()"
    baseline = _procedure(transformed, baseline_start, "END SUBROUTINE find_failed_baseline_pairs")
    baseline = _replace_once(
        baseline,
        "strict_mass_ratio=(pair==4))\n",
        "strict_mass_ratio=(pair==4), &\n"
        f"             inactive_mass_limit=MERGE({ICE_LIMIT_EXPRESSION},0.0_real64,pair==2))\n",
        "failed baseline pair diagnosis",
    )
    transformed = _replace_procedure(
        transformed, baseline_start, "END SUBROUTINE find_failed_baseline_pairs", baseline
    )

    prepared_start = "SUBROUTINE prepare_source_first_rates()"
    prepared = _procedure(transformed, prepared_start, "END SUBROUTINE prepare_source_first_rates")
    prepared = _replace_once(
        prepared,
        "allow_joint_quantum_absence=.TRUE.)\n        END IF\n",
        "allow_joint_quantum_absence=.TRUE., &\n"
        f"               inactive_mass_limit=MERGE({ICE_LIMIT_EXPRESSION},0.0_real64,p==2))\n        END IF\n",
        "source-prepared endpoint store",
    )
    prepared = _replace_once(
        prepared,
        "allow_joint_quantum_absence=.TRUE.)\n          IF (.NOT.full_valid)",
        "allow_joint_quantum_absence=.TRUE., &\n"
        f"                 inactive_mass_limit=MERGE({ICE_LIMIT_EXPRESSION},0.0_real64,p==2))\n"
        "          IF (.NOT.full_valid)",
        "source-prepared fallback store",
    )
    transformed = _replace_procedure(
        transformed, prepared_start, "END SUBROUTINE prepare_source_first_rates", prepared
    )
    return transformed


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"{label} anchor is missing or ambiguous")
    return source.replace(old, new, 1)


def _procedure(source: str, start: str, end: str) -> str:
    if source.count(start) != 1 or source.count(end) != 1:
        raise ValueError(f"{start} procedure anchor is missing or ambiguous")
    begin = source.index(start)
    finish = source.index(end, begin) + len(end)
    return source[begin:finish]


def _replace_procedure(source: str, start: str, end: str, replacement: str) -> str:
    old = _procedure(source, start, end)
    return source.replace(old, replacement, 1)
