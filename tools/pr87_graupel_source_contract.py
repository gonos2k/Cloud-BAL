"""Pin V23c grouped candidates to the exact graupel bulk-density contract."""
from __future__ import annotations

import hashlib


V23C_NATIVE_UPDATE_SHA256 = "0cff4ea924e77f03e283b0aee0caf53168e8753da443e59316cb44697857ad0c"


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise ValueError(f"expected one {label} anchor")
    return source.replace(old, new, 1)


def extend_graupel_strict_mass(source: str) -> str:
    """Enable exact QG/BG mass checks for pair 4, pinned to native V23c."""
    if hashlib.sha256(source.encode()).hexdigest() != V23C_NATIVE_UPDATE_SHA256:
        raise ValueError("graupel strict-mass source preimage differs from frozen V23c")

    source = _replace_once(
        source,
        "                         number_pair_bounds=number_bounds)\n",
        "                         number_pair_bounds=number_bounds, &\n"
        "                         strict_mass_pairs=[.FALSE.,.FALSE.,.FALSE.,.TRUE.])\n",
        "grouped strict-mass mask",
    )
    source = _replace_once(
        source,
        "  REAL(real32) :: source_stored(2),full_stored(2)\n",
        "  REAL(real32) :: source_stored(2),full_stored(2),source_check_stored(2)\n",
        "source-only strict-mass output",
    )
    source = _replace_once(
        source,
        "  LOGICAL :: full_valid,baseline_feasible,source_first_pair(4),failed_pairs(4)\n",
        "  LOGICAL :: full_valid,baseline_feasible,source_first_pair(4),failed_pairs(4),source_valid\n",
        "source-only strict-mass result",
    )

    full_diagnostic = (
        "        ELSE\n"
        "        CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &\n"
        "             minmass(p),maxmass(p),.TRUE.,full_stored(1),full_stored(2),adjustment,full_valid, &\n"
        "             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)\n"
        "        END IF\n"
        "        IF (.NOT.full_valid) THEN\n"
    )
    source = _replace_once(
        source,
        full_diagnostic,
        full_diagnostic.replace(
            "allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)",
            "allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &\n"
            "             strict_mass_ratio=(p==4))",
        ),
        "full-candidate graupel diagnostic",
    )

    baseline_diagnostic = (
        "        ELSE\n"
        "        CALL joint_moment_store(value(1),value(2),drydensity(c),minmass(pair),maxmass(pair), &\n"
        "             .TRUE.,stored(1),stored(2),local_adjustment,local_valid, &\n"
        "             allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)\n"
        "        END IF\n"
        "        IF (.NOT.local_valid) failed_pairs(pair)=.TRUE.\n"
    )
    source = _replace_once(
        source,
        baseline_diagnostic,
        baseline_diagnostic.replace(
            "allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE.)",
            "allow_normal_q_adjustment=.TRUE.,allow_joint_quantum_absence=.TRUE., &\n"
            "             strict_mass_ratio=(pair==4))",
        ),
        "baseline graupel diagnostic",
    )

    source_diagnostic = (
        "        source_stored=REAL(source_candidate,real32)\n"
        "        IF (.NOT.joint_moment_is_valid(source_stored(1),source_stored(2),drydensity(cell), &\n"
        "                                       minmass(p),maxmass(p))) THEN\n"
        "          source_failures=source_failures+1\n"
        "          WRITE(u,*) 'SOURCE',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &\n"
        "              qb(cell,p),nb(cell,p),qs64(cell,p),ns64(cell,p),source_candidate,source_stored,drydensity(cell)\n"
        "        END IF\n"
    )
    source = _replace_once(
        source,
        source_diagnostic,
        "        source_stored=REAL(source_candidate,real32)\n"
        "        IF (p==4) THEN\n"
        "          CALL joint_moment_store(source_candidate(1),source_candidate(2),drydensity(cell), &\n"
        "               minmass(p),maxmass(p),.TRUE.,source_check_stored(1),source_check_stored(2), &\n"
        "               adjustment,source_valid,allow_normal_q_adjustment=.TRUE., &\n"
        "               allow_joint_quantum_absence=.TRUE.,strict_mass_ratio=.TRUE.)\n"
        "        ELSE\n"
        "          source_valid=joint_moment_is_valid(source_stored(1),source_stored(2),drydensity(cell), &\n"
        "                                           minmass(p),maxmass(p))\n"
        "        END IF\n"
        "        IF (.NOT.source_valid) THEN\n"
        "          source_failures=source_failures+1\n"
        "          WRITE(u,*) 'SOURCE',rk,p,i,j,k,oldcarrier(cell),newcarrier(cell), &\n"
        "              qb(cell,p),nb(cell,p),qs64(cell,p),ns64(cell,p),source_candidate,source_stored,drydensity(cell)\n"
        "        END IF\n",
        "strict SOURCE graupel classifier",
    )
    return source
