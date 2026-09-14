"""Pure CP01 MP37 auxiliary-field contract validator.

This validates a candidate payload and its declared evidence.  It never fills,
clips, mutates, or writes fields, and a structural-valid result remains
diagnostic only.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from collections.abc import Mapping

import numpy as np


AUX_FIELDS = ("QNCCN", "QNCLOUD", "QNICE", "QNRAIN", "QIB")
EXPECTED_UNITS = {
    "QNCCN": "kg-1",
    "QNCLOUD": "kg-1",
    "QNICE": "kg-1",
    "QNRAIN": "kg-1",
    "QIB": "m3 kg-1",
}
DENOMINATORS = frozenset({"dry_air", "moist_air", "hydrometeor_mass"})
AUTHORITY_SCOPES = frozenset({"CONSTRUCTED_TEST_ONLY", "PRODUCER_BOUND"})
SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class FieldMetadata:
    """Required per-field declaration; text alone never supplies authority."""

    units: str
    denominator: str
    provenance: str


@dataclass(frozen=True)
class AuthorityEvidence:
    """Unverified evidence identifiers; authentication is a separate caller duty."""

    scope: str
    receipt_sha256: str
    source_sha256: str
    producer_sha256: str


def _result(status: str, reason: str, **extra: object) -> dict[str, object]:
    return {
        "status": status,
        "contract_valid": False,
        "accepted": False,
        "reason": reason,
        "native_authority": "NONE",
        "authority_verification": "NOT_PERFORMED",
        "promotion_eligible": False,
        "science_authority": "NONE",
        **extra,
    }


def _expected_denominator_issue(
    expected_denominators: Mapping[str, str] | None,
) -> str | None:
    if expected_denominators is None:
        return "EXPECTED_DENOMINATOR_MAPPING_MISSING"
    if not isinstance(expected_denominators, Mapping):
        return "INVALID_EXPECTED_DENOMINATOR_MAPPING"
    if set(expected_denominators) != set(AUX_FIELDS):
        return "INCOMPLETE_EXPECTED_DENOMINATOR_MAPPING"
    for name in AUX_FIELDS:
        value = expected_denominators[name]
        if not isinstance(value, str) or value not in DENOMINATORS:
            return f"UNKNOWN_EXPECTED_DENOMINATOR:{name}"
    return None


def _metadata_issue(
    metadata: Mapping[str, FieldMetadata],
    expected_denominators: Mapping[str, str],
) -> str | None:
    if not isinstance(metadata, Mapping):
        return "INVALID_METADATA_CONTAINER"
    for name in AUX_FIELDS:
        item = metadata.get(name)
        if item is None:
            return f"MISSING_METADATA:{name}"
        if not isinstance(item, FieldMetadata):
            return f"INVALID_METADATA_TYPE:{name}"
        if not isinstance(item.units, str) or item.units != EXPECTED_UNITS[name]:
            return f"UNEXPECTED_UNITS:{name}"
        if not isinstance(item.denominator, str) or item.denominator not in DENOMINATORS:
            return f"UNKNOWN_DENOMINATOR:{name}"
        if item.denominator != expected_denominators[name]:
            return f"DENOMINATOR_MISMATCH:{name}"
        if not isinstance(item.provenance, str) or not item.provenance.strip():
            return f"MISSING_PROVENANCE:{name}"
    return None


def _authority_issue(authority: AuthorityEvidence | None) -> str | None:
    if not isinstance(authority, AuthorityEvidence):
        return "AUTHORITY_EVIDENCE_MISSING"
    if not isinstance(authority.scope, str) or authority.scope not in AUTHORITY_SCOPES:
        return "AUTHORITY_SCOPE_UNSUPPORTED"
    for name, value in (
        ("receipt_sha256", authority.receipt_sha256),
        ("source_sha256", authority.source_sha256),
        ("producer_sha256", authority.producer_sha256),
    ):
        if not isinstance(value, str) or not SHA256.fullmatch(value):
            return f"INVALID_AUTHORITY_HASH:{name}"
    return None


def validate_mp37_auxiliaries(
    arrays: Mapping[str, np.ndarray],
    metadata: Mapping[str, FieldMetadata],
    authority: AuthorityEvidence | None,
    *,
    qgraup: np.ndarray,
    qrain: np.ndarray,
    qcloud: np.ndarray,
    qice: np.ndarray,
    expected_shape: tuple[int, int, int],
    expected_denominators: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Validate exact MP37 coverage without changing or synthesizing values.

    ``NO_AUTHORITY`` identifies missing declarations or unresolved mass/moment pairs.
    Malformed arrays are rejected before checking declarations or evidence.
    Missing declarations do not establish structural validity.
    ``REJECTED`` means malformed data cannot enter the handoff at all.
    All four hydrometeor mass fields are required for per-cell moment coverage.
    """
    if (not isinstance(expected_shape, tuple) or len(expected_shape) != 3
            or any(isinstance(size, bool) or not isinstance(size, (int, np.integer))
                   or int(size) <= 0 for size in expected_shape)):
        return _result("REJECTED", "INVALID_EXPECTED_SHAPE")
    if not isinstance(arrays, Mapping):
        return _result("REJECTED", "INVALID_ARRAY_CONTAINER")
    values: dict[str, np.ndarray] = {}
    mass_fields = {"QGRAUP": qgraup, "QRAIN": qrain,
                   "QCLOUD": qcloud, "QICE": qice}
    for name in (*AUX_FIELDS, *mass_fields):
        if name not in mass_fields and name not in arrays:
            return _result("REJECTED", f"MISSING_FIELD:{name}")
        value = mass_fields[name] if name in mass_fields else arrays[name]
        if np.ma.isMaskedArray(value):
            return _result("REJECTED", f"MASKED_FIELD:{name}")
        try:
            value = np.asarray(value)
        except (TypeError, ValueError):
            return _result("REJECTED", f"INVALID_ARRAY:{name}")
        if value.shape != expected_shape:
            return _result("REJECTED", f"MALFORMED_SHAPE:{name}")
        if not (np.issubdtype(value.dtype, np.integer)
                or np.issubdtype(value.dtype, np.floating)):
            return _result("REJECTED", f"NONREAL_FIELD:{name}")
        if not np.all(np.isfinite(value)):
            return _result("REJECTED", f"NONFINITE_FIELD:{name}")
        if np.any(value < 0):
            return _result("REJECTED", f"NEGATIVE_FIELD:{name}")
        values[name] = value

    issue = _expected_denominator_issue(expected_denominators)
    if issue is not None:
        status = "REJECTED" if issue == "INVALID_EXPECTED_DENOMINATOR_MAPPING" else "NO_AUTHORITY"
        return _result(status, issue)
    issue = _metadata_issue(metadata, expected_denominators)
    if issue is not None:
        status = "NO_AUTHORITY" if issue.startswith((
            "UNKNOWN_DENOMINATOR", "MISSING_PROVENANCE", "DENOMINATOR_MISMATCH")) else "REJECTED"
        return _result(status, issue)
    issue = _authority_issue(authority)
    if issue is not None:
        return _result("NO_AUTHORITY", issue)

    for mass, moment in (("QGRAUP", "QIB"), ("QRAIN", "QNRAIN"),
                         ("QCLOUD", "QNCLOUD"), ("QICE", "QNICE")):
        if np.any((values[mass] > 0) & (values[moment] == 0)):
            return _result("NO_AUTHORITY", f"{moment}_ZERO_WITH_NONZERO_{mass}")

    return {
        "status": "STRUCTURAL_CONTRACT_VALID",
        "contract_valid": True,
        "accepted": False,
        "reason": "EXACT_MP37_AUXILIARY_COVERAGE",
        "authority_scope": authority.scope,
        "native_authority": "NONE",
        "authority_verification": "NOT_PERFORMED",
        "promotion_eligible": False,
        "science_authority": "NONE",
        "synthesized_fields": [],
        "mutated_input": False,
    }
