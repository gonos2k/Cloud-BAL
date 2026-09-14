#!/usr/bin/env python3
"""Read-only MP37 wrfinput inspection; never authorizes or launches a model."""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from collections.abc import Mapping
from pathlib import Path

from netCDF4 import Dataset
import numpy as np

from cloud_bal_transaction import OutputTransaction, preflight_publication_filesystem
from mp37_aux_contract import (
    AUX_FIELDS,
    AuthorityEvidence,
    FieldMetadata,
    _result,
    validate_mp37_auxiliaries,
)


DIMENSIONS = ("Time", "bottom_top", "south_north", "west_east")
PAIRS = (("QGRAUP", "QIB"), ("QRAIN", "QNRAIN"),
         ("QCLOUD", "QNCLOUD"), ("QICE", "QNICE"))
_SHA256 = set("0123456789abcdef")
_PROFILE_DENOMINATORS = {name: "dry_air" for name in AUX_FIELDS}
_UNIT_ALIASES = {
    "kg-1": "kg-1",
    "kg(-1)": "kg-1",
    "m3 kg-1": "m3 kg-1",
    "m(3) kg(-1)": "m3 kg-1",
}


@dataclass(frozen=True)
class NativeAuxiliaryDeclaration:
    """Explicit auxiliary declarations bound to one input byte image.

    The declaration is evidence syntax, not authenticated native authority.  In
    particular, a ``PRODUCER_BOUND`` scope is still reported as unverified by
    the shared validator and cannot authorize a native launch.
    """

    input_sha256: str
    metadata: Mapping[str, FieldMetadata]
    expected_denominators: Mapping[str, str]
    authority: AuthorityEvidence


class NativePreflightRejected(RuntimeError):
    """A native input failed the maintained preflight boundary."""

    def __init__(self, report: dict[str, object]):
        self.report = report
        super().__init__(f"native preflight rejected: {report.get('reason', 'unknown')}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and set(value) <= _SHA256


def _declaration_binding_issue(
    declaration: NativeAuxiliaryDeclaration | None,
    input_sha256: str,
) -> str | None:
    if declaration is None:
        return None
    if not isinstance(declaration, NativeAuxiliaryDeclaration):
        return "DECLARATION_TYPE_INVALID"
    if not _valid_sha256(declaration.input_sha256):
        return "DECLARATION_INPUT_SHA256_UNKNOWN"
    if declaration.input_sha256 != input_sha256:
        return "DECLARATION_INPUT_SHA256_MISMATCH"
    return None


def _serialized_unit(variable: object) -> str | None:
    value = getattr(variable, "units", None)
    if isinstance(value, bytes):
        try:
            value = value.decode("ascii")
        except UnicodeDecodeError:
            return None
    if not isinstance(value, str):
        return None
    return _UNIT_ALIASES.get(value.strip())


def _declared_unit(value: object) -> str | None:
    if not isinstance(value, FieldMetadata):
        return None
    return _UNIT_ALIASES.get(value.units.strip())


def _unit_attribute_issue(
    dataset: Dataset,
    declaration: NativeAuxiliaryDeclaration,
) -> str | None:
    for name in AUX_FIELDS:
        declared = _declared_unit(declaration.metadata.get(name))
        if declared is None:
            continue
        serialized = _serialized_unit(dataset.variables[name])
        if serialized is None:
            return f"MISSING_OR_UNKNOWN_UNITS_ATTRIBUTE:{name}"
        if serialized != declared:
            return f"UNITS_ATTRIBUTE_MISMATCH:{name}"
    return None


def _denominator_profile_issue(
    declaration: NativeAuxiliaryDeclaration,
) -> str | None:
    expected = declaration.expected_denominators
    if not isinstance(expected, Mapping) or set(expected) != set(AUX_FIELDS):
        return None
    if dict(expected) != _PROFILE_DENOMINATORS:
        return "DECLARATION_DENOMINATOR_PROFILE_MISMATCH"
    return None


def inspect_dataset(
    dataset: Dataset,
    *,
    declaration: NativeAuxiliaryDeclaration | None = None,
    input_sha256: str | None = None,
) -> dict[str, object]:
    """Decode a single native time record without assuming denominator authority."""
    if "Time" not in dataset.dimensions or len(dataset.dimensions["Time"]) != 1:
        return _result("REJECTED", "INVALID_TIME_DIMENSION")
    fields = {}
    for name in (*AUX_FIELDS, *(mass for mass, _ in PAIRS)):
        if name not in dataset.variables:
            return _result("REJECTED", f"MISSING_FIELD:{name}")
        variable = dataset[name]
        if variable.dimensions != DIMENSIONS:
            return _result("REJECTED", f"MALFORMED_DIMENSIONS:{name}")
        value = variable[0]
        if np.any(np.ma.getmaskarray(value)):
            return _result("REJECTED", f"MASKED_FIELD:{name}")
        fields[name] = np.asarray(value)
        fields[name].flags.writeable = False

    shape = fields["QCLOUD"].shape
    # Preserve the reader's safety ordering: malformed serialized values are
    # rejected before a missing or conflicting declaration can hide them.
    array_report = validate_mp37_auxiliaries(
        {name: fields[name] for name in AUX_FIELDS},
        {}, None,
        qgraup=fields["QGRAUP"], qrain=fields["QRAIN"],
        qcloud=fields["QCLOUD"], qice=fields["QICE"], expected_shape=shape,
        expected_denominators=None,
    )
    if array_report["status"] == "REJECTED":
        return array_report
    if declaration is None:
        report = array_report
    else:
        binding_issue = _declaration_binding_issue(declaration, input_sha256 or "")
        if binding_issue is not None:
            return _result("REJECTED", binding_issue)
        profile_issue = _denominator_profile_issue(declaration)
        if profile_issue is not None:
            return _result("NO_AUTHORITY", profile_issue)
        report = validate_mp37_auxiliaries(
            {name: fields[name] for name in AUX_FIELDS},
            declaration.metadata,
            declaration.authority,
            qgraup=fields["QGRAUP"], qrain=fields["QRAIN"],
            qcloud=fields["QCLOUD"], qice=fields["QICE"],
            expected_shape=shape,
            expected_denominators=declaration.expected_denominators,
        )
    if report["status"] == "REJECTED":
        return report
    if report["status"] == "STRUCTURAL_CONTRACT_VALID" and declaration is not None:
        units_issue = _unit_attribute_issue(dataset, declaration)
        if units_issue is not None:
            return _result("REJECTED", units_issue)
    physics = getattr(dataset, "MP_PHYSICS", None)
    if physics is None:
        return _result("NO_AUTHORITY", "MISSING_MP_PHYSICS")
    physics = np.asarray(physics)
    if physics.ndim != 0 or physics.dtype.kind not in "ifu" or physics.item() != 37:
        return _result("REJECTED", "UNSUPPORTED_MP_PHYSICS")
    report.update(
        expected_shape=list(shape), mp_physics=37,
        pair_gap_counts={mass: int(np.count_nonzero(
            (fields[mass] > 0) & (fields[moment] == 0))) for mass, moment in PAIRS},
    )
    if declaration is not None:
        report.update(
            declaration_input_sha256=declaration.input_sha256,
            evidence_status="SYNTAX_ONLY_UNVERIFIED",
            native_promotion=False,
            launch_authority="NONE",
        )
    return report


def inspect_native_mp37(
    path: str | Path,
    *,
    declaration: NativeAuxiliaryDeclaration | None = None,
) -> dict[str, object]:
    path = Path(path)
    context = {"input": str(path.absolute()), "inspection_only": True}
    try:
        before = file_sha256(path)
        with Dataset(path, "r") as dataset:
            report = inspect_dataset(
                dataset, declaration=declaration, input_sha256=before
            )
        after = file_sha256(path)
    except (OSError, RuntimeError, ValueError, TypeError, IndexError) as error:
        return {**_result("REJECTED", "NATIVE_INPUT_READ_ERROR", detail=str(error)),
                **context}
    if before != after:
        return {**_result("REJECTED", "NATIVE_INPUT_CHANGED"), **context}
    return {**report, **context, "input_sha256": before, "input_unchanged": True}


def run_native_preflight(
    input_path: str | Path,
    *,
    publication_root: str | Path,
    transaction_id: str,
    source_commit: str,
    configuration: str,
    valid_time: int = 0,
    declaration: NativeAuxiliaryDeclaration | None = None,
) -> dict[str, object]:
    """Validate one native input and publish only a diagnostic receipt.

    The input is inspected directly; callers cannot supply a precomputed report.
    A malformed or unauthoritative input raises before ``OutputTransaction`` is
    begun, so an existing current generation remains the only accepted one.
    The sole positive path is an explicitly declared ``CONSTRUCTED_TEST_ONLY``
    contract, which publishes a diagnostic receipt with native promotion and
    launch authority disabled.
    """
    report = inspect_native_mp37(input_path, declaration=declaration)
    if report["status"] != "STRUCTURAL_CONTRACT_VALID":
        raise NativePreflightRejected(report)
    if report.get("authority_scope") != "CONSTRUCTED_TEST_ONLY":
        rejection = _result(
            "NO_AUTHORITY", "NATIVE_AUTHORITY_NOT_VERIFIED",
            input=report.get("input"), input_sha256=report.get("input_sha256"),
            input_unchanged=report.get("input_unchanged", False),
            inspection_only=True,
            evidence_status="SYNTAX_ONLY_UNVERIFIED",
            native_promotion=False, launch_authority="NONE",
        )
        raise NativePreflightRejected(rejection)

    transaction = OutputTransaction(publication_root, transaction_id)
    transaction.root.mkdir(parents=True, exist_ok=True)
    filesystem = preflight_publication_filesystem(transaction.root)
    receipt = {
        **report,
        "publication_filesystem_preflight": filesystem,
        "receipt_scope": "CONSTRUCTED_TEST_ONLY",
        "native_promotion": False,
        "launch_authority": "NONE",
        "inspection_only": True,
    }
    transaction.begin(
        ["preflight/native_mp37.json"],
        source_commit=source_commit,
        configuration=configuration,
        valid_time=valid_time,
    )
    output = transaction.resolve_output("preflight/native_mp37.json")
    output.write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return transaction.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="single-time wrfinput NetCDF file")
    args = parser.parse_args()
    report = inspect_native_mp37(args.input)
    print(json.dumps(report, indent=2, allow_nan=False))
    # No success code can be mistaken for permission to launch a native model.
    return 3 if report["status"] == "NO_AUTHORITY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
