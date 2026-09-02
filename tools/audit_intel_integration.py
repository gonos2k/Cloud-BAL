#!/usr/bin/env python3
"""Deterministic, read-only Intel integration audit for Cloud-BAL."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "cloud-bal-intel-integration-audit-v1"
RECEIPT_SCHEMA = "cloud-bal-ifx-build-receipt-v1"
EXPECTED_IFX = Path(
    "/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx"
)
EXPECTED_IFX_VERSION = "ifx (IFX) 2026.0.0 20260331"
EXPECTED_IFX_SHA256 = (
    "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef"
)
EXPECTED_IFX_COMMENT = (
    "Intel(R) oneAPI DPC++/C++ Compiler 2026.0.0 (2026.0.0.20260331)"
)

JOB = Path("ANAL/NE57/SHEL/klps_lc05_anal_all_ajob.csh")
BUILD_ROOT = Path("klaps-v5.0_")
COMMON_MAKEFILE = BUILD_ROOT / "src/include/makefile.inc"
TOP_MAKEFILE = BUILD_ROOT / "Makefile"
STAGES = {
    "deriv": {
        "makefile": BUILD_ROOT / "src/deriv/Makefile",
        "binary": Path("ANAL/NE57/EXET/klps_anal_derv.exe"),
        "executable": "klps_anal_derv.exe",
        "job_token": "${KL05EXET}/klps_anal_derv.exe",
        "adapter_token": "cloud_bal_deriv_adapter",
        "entry_symbol": "__cloud_bal_deriv_adapter_MOD_cloud_bal_deriv_entry",
    },
    "balance": {
        "makefile": BUILD_ROOT / "src/balance/Makefile",
        "binary": Path("ANAL/NE57/EXET/klps_anal_qbal.exe"),
        "executable": "klps_anal_qbal.exe",
        "job_token": "${KL05EXET}/klps_anal_qbal.exe",
        "adapter_token": "cloud_bal_balance_adapter",
        "entry_symbol": "__cloud_bal_balance_adapter_MOD_cloud_bal_balance_entry",
    },
    "lapsprep": {
        "makefile": BUILD_ROOT / "src/lapsprep/Makefile",
        "binary": Path("ANAL/NE57/EXET/klps_anal_prep.exe"),
        "executable": "klps_anal_prep.exe",
        "job_token": "${KL05EXET}/klps_anal_prep.exe",
        "adapter_token": "cloud_bal_lapsprep_adapter",
        "entry_symbol": "__cloud_bal_lapsprep_adapter_MOD_cloud_bal_lapsprep_entry",
    },
}
STAGE_ORDER = tuple(STAGES)

DEPENDENCY_ROOTS = ("NETCDF", "HDF5", "ZLIB", "SZLIB", "CURL")
DEPENDENCY_ARTIFACT_GROUPS = {
    "NETCDF": (
        ("include/netcdf.inc", "include/netcdf.mod"),
        ("lib/libnetcdf.so*", "lib/libnetcdf.a"),
        ("lib/libnetcdff.so*", "lib/libnetcdff.a"),
    ),
    "HDF5": (
        ("include/hdf5.h",),
        ("lib/libhdf5.so*", "lib/libhdf5.a"),
        ("lib/libhdf5_hl.so*", "lib/libhdf5_hl.a"),
    ),
    "ZLIB": (("lib/libz.so*", "lib/libz.a"),),
    "SZLIB": (("lib/libsz.so*", "lib/libsz.a"),),
    "CURL": (("include/curl/curl.h",), ("lib/libcurl.so*", "lib/libcurl.a")),
}
INSPECTION_TOOLS = ("readelf", "nm", "strings", "ldd")
FORBIDDEN_COMPILERS = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(ifort|gfortran|iftn|ftn|flang(?:-new)?|nvfortran|pgfortran|mpiifort|mpifort)"
    r"(?![A-Za-z0-9_])"
)
MAKE_ASSIGNMENT = re.compile(
    r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*(:=|\?=|\+=|=)\s*(.*?)\s*$"
)
NEEDED_LIBRARY = re.compile(r"Shared library:\s*\[([^]]+)\]")
MISSING_LIBRARY = re.compile(r"^\s*(\S+)\s+=>\s+not found\s*$")
UNDEFINED_SYMBOL = re.compile(r"undefined symbol:\s*([^\s(]+)")
COMPILER_SIGNATURE = re.compile(r".*Intel\(R\).*Fortran.*Version.*")
COMMON_INCLUDE = re.compile(
    r"^include\s+(?:\$\(SRCROOT\)|\$\{SRCROOT\})/src/include/makefile\.inc\s*$"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def run_command(argv: list[str], timeout: int = 30) -> dict[str, Any]:
    env = os.environ.copy()
    env["LC_ALL"] = "C"
    for name in (
        "LD_PRELOAD",
        "LD_AUDIT",
        "LD_DEBUG",
        "LD_DEBUG_OUTPUT",
        "LD_PROFILE",
        "LD_PROFILE_OUTPUT",
        "GCONV_PATH",
        "LOCPATH",
    ):
        env.pop(name, None)
    try:
        result = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"returncode": None, "stdout": "", "stderr": str(error)}
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def add_finding(
    findings: list[dict[str, str]], code: str, scope: str, message: str
) -> None:
    findings.append({"code": code, "scope": scope, "message": message})


def status(findings: Iterable[dict[str, str]], prefix: str) -> str:
    return (
        "BLOCKED"
        if any(item["scope"] == prefix or item["scope"].startswith(prefix + ".")
               for item in findings)
        else "GO"
    )


def active_make_lines(text: str) -> list[tuple[int, str]]:
    """Join continuations and discard comments without evaluating Make."""
    result: list[tuple[int, str]] = []
    pending = ""
    first = 0
    for number, physical in enumerate(text.splitlines(), 1):
        line = physical.split("#", 1)[0].rstrip()
        if not pending and not line:
            continue
        if not pending:
            first = number
        if line.endswith("\\"):
            pending += line[:-1] + " "
            continue
        pending += line
        if pending.strip():
            result.append((first, pending.strip()))
        pending = ""
    if pending.strip():
        result.append((first, pending.strip()))
    return result


def active_shell_lines(text: str) -> list[tuple[int, str]]:
    """Join csh continuations and discard blank/comment-only lines."""
    result: list[tuple[int, str]] = []
    pending = ""
    first = 0
    for number, physical in enumerate(text.splitlines(), 1):
        line = physical.split("#", 1)[0].strip()
        if not pending and not line:
            continue
        if not pending:
            first = number
        if line.endswith("\\"):
            pending += line[:-1].rstrip() + " "
            continue
        pending += line
        if pending.strip():
            result.append((first, pending.strip()))
        pending = ""
    if pending.strip():
        result.append((first, pending.strip()))
    return result


def make_assignments(lines: Iterable[tuple[int, str]]) -> dict[str, str]:
    values: dict[str, str] = {}
    for _, line in lines:
        match = MAKE_ASSIGNMENT.match(line)
        if not match:
            continue
        name, operator, value = match.groups()
        value = value.strip()
        if operator == "?=" and name in values:
            continue
        if operator == "+=" and name in values:
            value = f"{values[name]} {value}".strip()
        values[name] = value
    return values


def expand_make(value: str, assignments: dict[str, str]) -> str:
    variable = re.compile(r"\$\(([^)]+)\)|\$\{([^}]+)\}")
    expanded = value
    for _ in range(12):
        replaced = variable.sub(
            lambda match: assignments.get(
                match.group(1) or match.group(2), match.group(0)
            ),
            expanded,
        )
        if replaced == expanded:
            break
        expanded = replaced
    return expanded


def is_pinned_compiler(
    value: str, assignments: dict[str, str], ifx: Path
) -> bool:
    value = expand_make(value.strip(), assignments)
    if value in ("$(CLOUD_BAL_FC)", "${CLOUD_BAL_FC}"):
        return True
    candidate = Path(value)
    return candidate.is_absolute() and candidate.resolve() == ifx.resolve()


def inspect_compiler(
    ifx: Path,
    expected_version: str,
    expected_hash: str,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    scope = "compiler"
    report: dict[str, Any] = {"path": str(ifx)}
    executable = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if not ifx.is_file() or not ifx.stat().st_mode & executable:
        add_finding(findings, "IFX_NOT_EXECUTABLE", scope, str(ifx))
        report["status"] = "BLOCKED"
        return report
    resolved = ifx.resolve()
    version_result = run_command([str(resolved), "--version"])
    version_lines = (version_result["stdout"] or version_result["stderr"]).splitlines()
    version = version_lines[0].strip() if version_lines else ""
    actual_hash = sha256(resolved)
    report.update({"resolved_path": str(resolved), "version": version, "sha256": actual_hash})
    if resolved.name != "ifx":
        add_finding(findings, "COMPILER_NOT_IFX", scope, resolved.name)
    if version_result["returncode"] != 0 or version != expected_version:
        add_finding(
            findings,
            "IFX_VERSION_MISMATCH",
            scope,
            f"found {version!r}; expected {expected_version!r}",
        )
    if actual_hash != expected_hash:
        add_finding(
            findings,
            "IFX_HASH_MISMATCH",
            scope,
            f"found {actual_hash}; expected {expected_hash}",
        )
    report["status"] = status(findings, scope)
    return report


def inspect_job(workspace: Path, findings: list[dict[str, str]]) -> dict[str, Any]:
    scope = "job"
    path = workspace / JOB
    report: dict[str, Any] = {"path": str(path)}
    if not path.is_file():
        add_finding(findings, "JOB_SCRIPT_MISSING", scope, str(path))
        report["status"] = "BLOCKED"
        return report
    active = active_shell_lines(read_text(path))
    depth = 0
    scoped: list[tuple[int, str, int]] = []
    for number, line in active:
        if re.match(r"^(?:endif|end|endsw)\b", line):
            depth = max(0, depth - 1)
        scoped.append((number, line, depth))
        if (
            re.match(r"^if\s*\(.*\)\s*then\s*$", line)
            or re.match(r"^(?:foreach|while|switch)\b", line)
        ):
            depth += 1
    report["sha256"] = sha256(path)
    legacy_modules = [
        {"line": number, "text": line}
        for number, line in active
        if (
            re.match(r"^(?:module\s+load|ml)\b", line)
            and re.search(r"\b(?:intel|oneapi)(?:/|\b)", line, re.IGNORECASE)
        )
        or (
            re.match(r"^source\s+", line)
            and re.search(r"(?:intel|oneapi).*(?:setvars|vars)", line, re.IGNORECASE)
        )
    ]
    if legacy_modules:
        add_finding(
            findings,
            "JOB_UNPINNED_INTEL_ENVIRONMENT",
            scope,
            "; ".join(item["text"] for item in legacy_modules),
        )

    expected_root = (workspace / "ANAL/NE57/EXET").resolve()
    roots = [
        (number, match.group(1))
        for number, line in active
        if (match := re.match(r"^setenv\s+KL05EXET\s+(\S+)\s*$", line))
    ]
    root_mutations = [
        number
        for number, line in active
        if re.match(r"^(?:setenv|unsetenv)\s+KL05EXET\b", line)
        or re.match(r"^set\s+KL05EXET\s*=", line)
    ]
    bound_root = None
    binding_line = -1
    if len(roots) == 1 and Path(roots[0][1]).is_absolute():
        binding_line, value = roots[0]
        bound_root = Path(value).resolve()
    source_after_binding = any(
        number > binding_line and re.match(r"^source\s+", line)
        for number, line in active
    )
    if (
        bound_root != expected_root
        or len(root_mutations) != 1
        or source_after_binding
    ):
        add_finding(
            findings,
            "JOB_EXECUTABLE_ROOT_UNRESOLVED",
            scope,
            f"KL05EXET must be the final explicit binding to {expected_root}",
        )
    report["executable_root"] = str(bound_root) if bound_root else None

    invocations: list[dict[str, Any]] = []
    order: list[int] = []
    commands: list[str] = []
    for stage in STAGE_ORDER:
        executable = str(STAGES[stage]["executable"])
        command = re.compile(
            r"^(?:mpiexec\s+-n\s+[0-9]+\s+)?"
            r"(?:\$\{KL05EXET\}|\$KL05EXET)/"
            + re.escape(executable)
            + r"(?:\s|\\|$)"
        )
        matches = [
            (number, line)
            for number, line, control_depth in scoped
            if control_depth == 0 and command.match(line)
        ]
        lines = [number for number, _ in matches]
        invocations.append({"stage": stage, "lines": lines})
        if len(lines) != 1:
            add_finding(
                findings,
                "JOB_STAGE_INVOCATION_COUNT",
                f"{scope}.{stage}",
                f"expected one active invocation; found {len(lines)}",
            )
        order.append(lines[0] if len(lines) == 1 else -1)
        commands.append(matches[0][1] if len(matches) == 1 else "")
    if all(line >= 0 for line in order) and order != sorted(order):
        add_finding(
            findings,
            "JOB_STAGE_ORDER_MISMATCH",
            scope,
            "expected deriv -> balance -> lapsprep",
        )
    if all(line >= 0 for line in order) and order == sorted(order):
        for index, stage in enumerate(STAGE_ORDER):
            command_line = order[index]
            next_line = order[index + 1] if index + 1 < len(order) else 10**9
            completion_line = command_line
            if "&" in commands[index]:
                waits = [
                    number
                    for number, line, control_depth in scoped
                    if control_depth == 0
                    and command_line < number < next_line
                    and re.match(r"^wait(?:\s|$)", line)
                ]
                if not waits:
                    add_finding(
                        findings,
                        "JOB_STAGE_COMPLETION_UNPROVEN",
                        f"{scope}.{stage}",
                        "background stage has no top-level wait",
                    )
                    continue
                completion_line = waits[-1]
            guarded = any(
                control_depth == 0
                and completion_line < number < next_line
                and re.match(
                    r"^if\s*\(\s*\$status\s*!=\s*0\s*\)\s*exit\s+[1-9][0-9]*\s*$",
                    line,
                )
                for number, line, control_depth in scoped
            )
            if not guarded:
                add_finding(
                    findings,
                    "JOB_STAGE_STATUS_UNCHECKED",
                    f"{scope}.{stage}",
                    "no top-level nonzero $status exit after completion",
                )
    report["invocations"] = invocations
    report["status"] = status(findings, scope)
    return report


def target_exists(lines: list[tuple[int, str]], target: str) -> bool:
    return any(re.match(r"^" + re.escape(target) + r"\s*:", line) for _, line in lines)


def make_contract_issues(
    lines: list[tuple[int, str]], require_common_include: bool
) -> list[str]:
    issues: list[str] = []
    includes = [line for _, line in lines if re.match(r"^(?:-?include|sinclude)\b", line)]
    expected = [line for line in includes if COMMON_INCLUDE.match(line)]
    if require_common_include and len(expected) != 1:
        issues.append("exact common include required once")
    if len(includes) != len(expected):
        issues.append("unreviewed include directive")
    if any(re.match(r"^override\b", line) for _, line in lines):
        issues.append("override directive")
    if any("$(eval" in line or "${eval" in line for _, line in lines):
        issues.append("eval expansion")
    return issues


def make_rules(lines: list[tuple[int, str]], executable: str) -> dict[str, dict[str, Any]]:
    rules: dict[str, dict[str, Any]] = {}
    current: list[str] = []
    for _, line in lines:
        match = re.match(r"^([^:=]+):\s*(.*)$", line)
        if match and not MAKE_ASSIGNMENT.match(line):
            targets = match.group(1).split()
            dependencies = match.group(2).split()
            normalize = lambda item: executable if item in ("$(EXE)", "${EXE}") else item
            current = [normalize(item) for item in targets]
            for target in current:
                rule = rules.setdefault(target, {"dependencies": [], "recipes": []})
                rule["dependencies"].extend(normalize(item) for item in dependencies)
            continue
        if current and not MAKE_ASSIGNMENT.match(line):
            for target in current:
                rules[target]["recipes"].append(line)
    return rules


def adapter_is_on_link_path(lines: list[tuple[int, str]], executable: str) -> bool:
    rules = make_rules(lines, executable)
    link = rules.get(executable)
    if not link:
        return False
    link_text = "\n".join(link["dependencies"] + link["recipes"])
    direct_link = (
        ("$(FC)" in link_text or "${FC}" in link_text)
        and ("$(CLOUD_BAL_ADAPTER)" in link_text or "${CLOUD_BAL_ADAPTER}" in link_text)
        and "-o" in link_text
    )
    reachable = {"all"}
    pending = ["all"]
    while pending:
        target = pending.pop()
        for dependency in rules.get(target, {}).get("dependencies", []):
            if dependency not in reachable:
                reachable.add(dependency)
                pending.append(dependency)
    return direct_link and executable in reachable


def artifact_valid(path: Path) -> bool:
    try:
        data = path.read_bytes()
    except OSError:
        return False
    name = path.name.lower()
    if ".so" in name:
        if len(data) < 20 or data[:4] != b"\x7fELF" or data[4:6] != b"\x02\x01":
            return False
        return int.from_bytes(data[18:20], "little") == 62
    if name.endswith(".a"):
        return data.startswith(b"!<arch>\n")
    if name.endswith(".mod"):
        return len(data) >= 64
    text = data.decode("latin-1", errors="ignore").upper()
    if name == "netcdf.inc":
        return "NF_" in text
    if name == "hdf5.h":
        return "H5" in text
    if name == "curl.h":
        return "CURL" in text
    return bool(data.strip())


def dependency_ready(root: Path, groups: tuple[tuple[str, ...], ...]) -> bool:
    return all(
        any(
            candidate.is_file() and artifact_valid(candidate)
            for pattern in alternatives
            for candidate in root.glob(pattern)
        )
        for alternatives in groups
    )


def inspect_makefiles(
    workspace: Path, ifx: Path, findings: list[dict[str, str]]
) -> dict[str, Any]:
    scope = "makefiles"
    common_path = workspace / COMMON_MAKEFILE
    top_path = workspace / TOP_MAKEFILE
    report: dict[str, Any] = {
        "common": {"path": str(common_path)},
        "top": {"path": str(top_path)},
        "stages": {},
    }
    if not common_path.is_file():
        add_finding(findings, "COMMON_MAKEFILE_MISSING", scope, str(common_path))
        common_lines: list[tuple[int, str]] = []
    else:
        common_lines = active_make_lines(read_text(common_path))
        report["common"]["sha256"] = sha256(common_path)
        for issue in make_contract_issues(common_lines, False):
            add_finding(findings, "MAKEFILE_UNSUPPORTED_CONTROL", f"{scope}.common", issue)
    if not top_path.is_file():
        add_finding(findings, "TOP_MAKEFILE_MISSING", scope, str(top_path))
    else:
        top_lines = active_make_lines(read_text(top_path))
        report["top"]["sha256"] = sha256(top_path)
        for issue in make_contract_issues(top_lines, True):
            add_finding(findings, "MAKEFILE_UNSUPPORTED_CONTROL", f"{scope}.top", issue)
        forbidden_top = sorted(
            set(FORBIDDEN_COMPILERS.findall("\n".join(line for _, line in top_lines)))
        )
        if forbidden_top:
            add_finding(
                findings,
                "MAKEFILE_FORBIDDEN_COMPILER",
                f"{scope}.top",
                ", ".join(forbidden_top),
            )
        missing_targets = [name for name in ("cleanlib", "lib") if not target_exists(top_lines, name)]
        if missing_targets:
            add_finding(
                findings,
                "COPIED_LINK_TARGET_MISSING",
                scope,
                "top Makefile lacks " + ", ".join(missing_targets),
            )

    library_root = workspace / BUILD_ROOT / "src/lib"
    closure_makefiles = sorted(library_root.rglob("Makefile")) if library_root.is_dir() else []
    report["library_closure_makefiles"] = [str(path) for path in closure_makefiles]
    if not closure_makefiles:
        add_finding(
            findings,
            "LIBRARY_CLOSURE_MISSING",
            f"{scope}.library_closure",
            str(library_root),
        )
    for path in closure_makefiles:
        lines = active_make_lines(read_text(path))
        closure_scope = f"{scope}.library_closure"
        for issue in make_contract_issues(lines, True):
            add_finding(
                findings,
                "MAKEFILE_UNSUPPORTED_CONTROL",
                closure_scope,
                f"{path}: {issue}",
            )
        forbidden = sorted(
            set(FORBIDDEN_COMPILERS.findall("\n".join(line for _, line in lines)))
        )
        if forbidden:
            add_finding(
                findings,
                "MAKEFILE_FORBIDDEN_COMPILER",
                closure_scope,
                f"{path}: {', '.join(forbidden)}",
            )

    common_assignments = make_assignments(common_lines)
    common_text = "\n".join(line for _, line in common_lines)
    forbidden_common = sorted(set(FORBIDDEN_COMPILERS.findall(common_text)))
    if forbidden_common:
        add_finding(
            findings,
            "MAKEFILE_FORBIDDEN_COMPILER",
            f"{scope}.common",
            ", ".join(forbidden_common),
        )

    dependencies: dict[str, dict[str, str]] = {}
    for name in DEPENDENCY_ROOTS:
        raw = common_assignments.get(name)
        if raw is None:
            add_finding(findings, "DEPENDENCY_ROOT_UNDECLARED", f"{scope}.{name}", name)
            dependencies[name] = {"status": "BLOCKED", "path": ""}
            continue
        value = expand_make(raw, common_assignments)
        root = Path(value)
        code = None
        if not root.is_absolute():
            code = "DEPENDENCY_ROOT_NOT_ABSOLUTE"
        elif not root.is_dir():
            code = "DEPENDENCY_ROOT_MISSING"
        elif not dependency_ready(root, DEPENDENCY_ARTIFACT_GROUPS[name]):
            code = "DEPENDENCY_ARTIFACT_MISSING"
        if code:
            add_finding(findings, code, f"{scope}.{name}", value)
        dependencies[name] = {"status": "BLOCKED" if code else "GO", "path": value}
    report["dependencies"] = dependencies

    for stage in STAGE_ORDER:
        stage_scope = f"{scope}.{stage}"
        path = workspace / Path(str(STAGES[stage]["makefile"]))
        stage_report: dict[str, Any] = {"path": str(path)}
        report["stages"][stage] = stage_report
        if not path.is_file():
            add_finding(findings, "STAGE_MAKEFILE_MISSING", stage_scope, str(path))
            stage_report["status"] = "BLOCKED"
            continue
        lines = active_make_lines(read_text(path))
        for issue in make_contract_issues(lines, True):
            add_finding(
                findings, "MAKEFILE_UNSUPPORTED_CONTROL", stage_scope, issue
            )
        assignments = dict(common_assignments)
        assignments.update(make_assignments(lines))
        active_text = "\n".join(line for _, line in lines)
        forbidden = sorted(set(FORBIDDEN_COMPILERS.findall(active_text)))
        if forbidden:
            add_finding(
                findings,
                "MAKEFILE_FORBIDDEN_COMPILER",
                stage_scope,
                ", ".join(forbidden),
            )
        for variable in ("FC", "CPP"):
            value = assignments.get(variable)
            if value is None:
                add_finding(
                    findings, "MAKEFILE_COMPILER_UNDECLARED", stage_scope, variable
                )
            elif not is_pinned_compiler(value, assignments, ifx):
                add_finding(
                    findings,
                    "MAKEFILE_COMPILER_NOT_PINNED_IFX",
                    stage_scope,
                    f"{variable}={value}",
                )
        adapter = str(STAGES[stage]["adapter_token"])
        adapter_source = f"{adapter}.f90"
        assigned = expand_make(assignments.get("CLOUD_BAL_ADAPTER", ""), assignments)
        recipe_uses_adapter = adapter_is_on_link_path(
            lines, str(STAGES[stage]["executable"])
        )
        source_exists = (path.parent / adapter_source).is_file()
        if assigned != adapter_source or not recipe_uses_adapter or not source_exists:
            add_finding(
                findings,
                "CANONICAL_SOURCE_NOT_LINKED",
                stage_scope,
                f"require linked {adapter_source}",
            )
        missing_targets = [name for name in ("all", "clean") if not target_exists(lines, name)]
        if missing_targets:
            add_finding(
                findings,
                "COPIED_LINK_TARGET_MISSING",
                stage_scope,
                "missing " + ", ".join(missing_targets),
            )
        stage_report.update(
            {
                "sha256": sha256(path),
                "adapter": adapter_source if assigned == adapter_source else assigned,
                "status": status(findings, stage_scope),
            }
        )
    report["status"] = status(findings, scope)
    return report


def inspect_receipt(
    receipt_path: Path,
    binary: Path,
    binary_hash: str,
    ifx: Path,
    expected_version: str,
    expected_hash: str,
    scope: str,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    report: dict[str, Any] = {"path": str(receipt_path)}
    if not receipt_path.is_file():
        add_finding(findings, "BINARY_IFX_PROVENANCE_MISSING", scope, str(receipt_path))
        report["status"] = "BLOCKED"
        return report
    try:
        content = json.loads(read_text(receipt_path))
    except (OSError, json.JSONDecodeError) as error:
        content = None
        reason = str(error)
    else:
        reason = "receipt must be a JSON object"
    if not isinstance(content, dict):
        add_finding(findings, "BINARY_IFX_PROVENANCE_INVALID", scope, reason)
        report["status"] = "BLOCKED"
        return report
    expected = {
        "schema": RECEIPT_SCHEMA,
        "binary_sha256": binary_hash,
        "compiler_path": str(ifx.resolve()),
        "compiler_version": expected_version,
        "compiler_sha256": expected_hash,
    }
    mismatch = [key for key, value in expected.items() if content.get(key) != value]
    command = content.get("link_command")
    command_ok = (
        isinstance(command, list)
        and bool(command)
        and all(isinstance(item, str) for item in command)
        and Path(command[0]).is_absolute()
        and Path(command[0]).resolve() == ifx.resolve()
        and not FORBIDDEN_COMPILERS.search(" ".join(command))
    )
    if command_ok:
        output_positions = [index for index, item in enumerate(command[:-1]) if item == "-o"]
        output = Path(command[output_positions[0] + 1]) if len(output_positions) == 1 else None
        command_ok = (
            len(output_positions) == 1
            and output is not None
            and output.is_absolute()
            and output.resolve() == binary.resolve()
        )
    if not command_ok:
        mismatch.append("link_command")
    if mismatch:
        add_finding(
            findings,
            "BINARY_IFX_PROVENANCE_MISMATCH",
            scope,
            "mismatched " + ", ".join(sorted(mismatch)),
        )
    report.update({"sha256": sha256(receipt_path), "status": "BLOCKED" if mismatch else "GO"})
    return report


def inspect_binary(
    stage: str,
    workspace: Path,
    ifx: Path,
    expected_version: str,
    expected_hash: str,
    tools: dict[str, str],
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    scope = f"binaries.{stage}"
    path = workspace / Path(str(STAGES[stage]["binary"]))
    report: dict[str, Any] = {"path": str(path)}
    executable_bits = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH
    if not path.is_file():
        add_finding(findings, "OPERATIONAL_BINARY_MISSING", scope, str(path))
        report["status"] = "BLOCKED"
        return report
    if path.is_symlink():
        add_finding(findings, "OPERATIONAL_BINARY_IS_SYMLINK", scope, str(path))
    if not path.stat().st_mode & executable_bits:
        add_finding(findings, "OPERATIONAL_BINARY_NOT_EXECUTABLE", scope, str(path))

    before = sha256(path)
    commands = {
        "header": [tools["readelf"], "-hW", str(path)],
        "dynamic": [tools["readelf"], "-dW", str(path)],
        "comment": [tools["readelf"], "-p", ".comment", str(path)],
        "symbols": [tools["nm"], "-a", "--defined-only", str(path)],
        "strings": [tools["strings"], str(path)],
        "relocations": [tools["ldd"], "-r", str(path)],
    }
    results = {name: run_command(argv) for name, argv in commands.items()}
    for name, result in results.items():
        if result["returncode"] != 0:
            add_finding(
                findings,
                "BINARY_INSPECTION_COMMAND_FAILED",
                scope,
                f"{name} returned {result['returncode']}",
            )
    if sha256(path) != before:
        add_finding(findings, "BINARY_CHANGED_DURING_AUDIT", scope, str(path))

    dynamic = results["dynamic"]["stdout"]
    relocation = results["relocations"]["stdout"] + "\n" + results["relocations"]["stderr"]
    needed_libraries = sorted(set(NEEDED_LIBRARY.findall(dynamic)))
    missing_libraries = sorted(
        match.group(1)
        for line in relocation.splitlines()
        if (match := MISSING_LIBRARY.match(line))
    )
    unresolved_symbols = sorted(set(UNDEFINED_SYMBOL.findall(relocation)))
    if missing_libraries:
        add_finding(
            findings, "BINARY_LIBRARY_NOT_FOUND", scope, ", ".join(missing_libraries)
        )
    if unresolved_symbols:
        add_finding(
            findings,
            "BINARY_UNRESOLVED_SYMBOLS",
            scope,
            f"{len(unresolved_symbols)}; first {', '.join(unresolved_symbols[:8])}",
        )
    forbidden_runtimes = sorted(
        name
        for name in needed_libraries
        if name.startswith("libgfortran") or name.startswith("libquadmath")
    )
    if forbidden_runtimes:
        add_finding(
            findings,
            "BINARY_FORBIDDEN_FORTRAN_RUNTIME",
            scope,
            ", ".join(forbidden_runtimes),
        )

    entry_symbol = str(STAGES[stage]["entry_symbol"]).lower()
    canonical_symbols = sorted(
        {
            fields[-1]
            for line in results["symbols"]["stdout"].splitlines()
            if (fields := line.split())
            and len(fields) >= 2
            and fields[-2].isupper()
            and fields[-1].lower() == entry_symbol
        }
    )
    if not canonical_symbols:
        add_finding(
            findings,
            "BINARY_CANONICAL_SYMBOLS_MISSING",
            scope,
            f"no global defined {entry_symbol} symbol",
        )

    if EXPECTED_IFX_COMMENT not in results["comment"]["stdout"]:
        add_finding(
            findings,
            "BINARY_IFX_COMMENT_MISSING",
            scope,
            "expected pinned IntelLLVM .comment entry is absent",
        )

    signatures = sorted(
        {
            line.strip()
            for line in results["strings"]["stdout"].splitlines()
            if COMPILER_SIGNATURE.match(line.strip())
        }
    )
    legacy = [
        item
        for item in signatures
        if "Fortran Intel(R) 64 Compiler" in item or "ifort" in item.lower()
    ]
    if legacy:
        add_finding(findings, "BINARY_LEGACY_IFORT_SIGNATURE", scope, legacy[0])

    receipt = inspect_receipt(
        Path(str(path) + ".ifx.json"),
        path,
        before,
        ifx,
        expected_version,
        expected_hash,
        scope,
        findings,
    )
    report.update(
        {
            "sha256": before,
            "needed_libraries": needed_libraries,
            "missing_libraries": missing_libraries,
            "unresolved_symbols": unresolved_symbols,
            "canonical_symbols": canonical_symbols,
            "compiler_signatures": signatures,
            "build_receipt": receipt,
            "status": status(findings, scope),
        }
    )
    return report


def scratch_root_safe(repo_root: Path) -> bool:
    scratch = repo_root / "scratch"
    if scratch.is_symlink() or (scratch.exists() and not scratch.is_dir()):
        return False
    return scratch.resolve().parent == repo_root.resolve()


def copied_tree_link_plan(workspace: Path, repo_root: Path, ifx: Path) -> dict[str, Any]:
    source = workspace / BUILD_ROOT
    copy_root = '"$cloud_bal_link_copy/klaps-v5.0_"'
    compiler = shlex.quote(str(ifx.resolve()))
    scratch = repo_root / "scratch"
    inner = "\n".join(
        [
            'root="$CLOUD_BAL_LINK_COPY/klaps-v5.0_"',
            '/usr/bin/make -C "$root" cleanlib FC="$CLOUD_BAL_FC" CPP="$CLOUD_BAL_FC"',
            *[
                f'/usr/bin/make -C "$root/src/{stage}" clean '
                'FC="$CLOUD_BAL_FC" CPP="$CLOUD_BAL_FC"'
                for stage in STAGE_ORDER
            ],
            '/usr/bin/make -C "$root" lib FC="$CLOUD_BAL_FC" CPP="$CLOUD_BAL_FC"',
            *[
                f'/usr/bin/make -C "$root/src/{stage}" all '
                'FC="$CLOUD_BAL_FC" CPP="$CLOUD_BAL_FC"'
                for stage in STAGE_ORDER
            ],
        ]
    )
    commands = [
        "set -euo pipefail",
        "unset MAKEFLAGS MAKEFILES MFLAGS GNUMAKEFLAGS BASH_ENV ENV CDPATH",
        f"test ! -L {shlex.quote(str(scratch))}",
        f"/usr/bin/mkdir -p {shlex.quote(str(scratch))}",
        f"test \"$(/usr/bin/readlink -f {shlex.quote(str(scratch))})\" = "
        f"{shlex.quote(str(scratch.resolve()))}",
        f"cloud_bal_link_copy=$(/usr/bin/mktemp -d {shlex.quote(str(scratch))}/ifx-link.XXXXXX)",
        "trap 'printf \"copied link tree retained: %s\\n\" \"$cloud_bal_link_copy\" >&2' EXIT",
        "if /usr/bin/find "
        + " ".join(
            [shlex.quote(str(source / "Makefile"))]
            + [
                shlex.quote(str(source / "src" / name))
                for name in ("include", "lib", "deriv", "balance", "lapsprep")
            ]
        )
        + " -type l -print -quit | /usr/bin/grep -q .; then "
        + "printf '%s\\n' 'source symlink rejected' >&2; exit 2; fi",
        f"/usr/bin/mkdir -p {copy_root}/src \"$cloud_bal_link_copy/home\"",
        f"/usr/bin/cp -a --reflink=auto {shlex.quote(str(source / 'Makefile'))} {copy_root}/",
        "/usr/bin/cp -a --reflink=auto "
        + " ".join(
            shlex.quote(str(source / "src" / name))
            for name in ("include", "lib", "deriv", "balance", "lapsprep")
        )
        + f" {copy_root}/src/",
        "/usr/bin/bwrap --die-with-parent --unshare-all --new-session "
        '--ro-bind / / --bind "$cloud_bal_link_copy" "$cloud_bal_link_copy" '
        "--tmpfs /tmp --proc /proc --dev /dev --clearenv "
        '--setenv HOME "$cloud_bal_link_copy/home" --setenv PATH /usr/bin:/bin '
        f"--setenv CLOUD_BAL_FC {compiler} "
        '--setenv CLOUD_BAL_LINK_COPY "$cloud_bal_link_copy" '
        "/bin/bash -ceu "
        + shlex.quote(inner),
    ]
    bwrap = Path("/usr/bin/bwrap")
    return {
        "status": "IDENTIFIED_NOT_EXECUTED",
        "mutates_original_tree": False,
        "original_tree_mount": "read-only inside bubblewrap",
        "sandbox_execution_verified": False,
        "sandbox": {
            "path": str(bwrap),
            "sha256": sha256(bwrap) if bwrap.is_file() else None,
        },
        "copy_payload": [
            str(BUILD_ROOT / "Makefile"),
            *[
                str(BUILD_ROOT / "src" / name)
                for name in ("include", "lib", "deriv", "balance", "lapsprep")
            ],
        ],
        "shell_commands": commands,
    }


def locate_tools(findings: list[dict[str, str]]) -> tuple[dict[str, str], dict[str, str | None]]:
    paths: dict[str, str] = {}
    hashes: dict[str, str | None] = {}
    for name in INSPECTION_TOOLS:
        path = Path("/usr/bin") / name
        paths[name] = str(path)
        hashes[name] = sha256(path) if path.is_file() else None
        if not path.is_file():
            add_finding(findings, "INSPECTION_TOOL_MISSING", "audit_tools", str(path))
    return paths, hashes


def audit(
    workspace: Path,
    repo_root: Path,
    ifx: Path,
    expected_version: str,
    expected_hash: str,
) -> dict[str, Any]:
    workspace = workspace.resolve()
    repo_root = repo_root.resolve()
    if workspace != repo_root.parent:
        raise ValueError("workspace must be the direct parent of Cloud-BAL")
    if not (repo_root / "tests/intel_toolchain.sh").is_file():
        raise ValueError("tests/intel_toolchain.sh is missing")

    findings: list[dict[str, str]] = []
    if not scratch_root_safe(repo_root):
        add_finding(
            findings,
            "SCRATCH_ROOT_UNSAFE",
            "audit_output",
            str(repo_root / "scratch"),
        )
    tools, tool_hashes = locate_tools(findings)
    report: dict[str, Any] = {
        "schema": SCHEMA,
        "workspace_root": str(workspace),
        "cloud_bal_root": str(repo_root),
        "inspection_tools": {
            name: {"path": tools[name], "sha256": tool_hashes[name]}
            for name in INSPECTION_TOOLS
        },
    }
    report["compiler"] = inspect_compiler(ifx, expected_version, expected_hash, findings)
    report["job"] = inspect_job(workspace, findings)
    report["makefiles"] = inspect_makefiles(workspace, ifx, findings)
    report["binaries"] = {
        stage: inspect_binary(
            stage,
            workspace,
            ifx,
            expected_version,
            expected_hash,
            tools,
            findings,
        )
        for stage in STAGE_ORDER
    }
    report["copied_tree_full_link_plan"] = copied_tree_link_plan(workspace, repo_root, ifx)
    findings.sort(key=lambda item: (item["code"], item["scope"], item["message"]))
    report["findings"] = findings
    report["summary"] = {
        "status": "BLOCKED" if findings else "GO",
        "blocker_count": len(findings),
        "blocker_codes": sorted({item["code"] for item in findings}),
        "build_attempted": False,
        "audit_writes_original_tree": False,
        "selected_binary_changed_during_audit": any(
            item["code"] == "BINARY_CHANGED_DURING_AUDIT" for item in findings
        ),
    }
    return report


def write_json(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise


def require_safe_output(path: Path, workspace: Path, repo_root: Path) -> Path:
    if workspace.resolve() != repo_root.resolve().parent:
        raise ValueError("workspace must be the direct parent of Cloud-BAL")
    scratch_path = repo_root / "scratch"
    if not scratch_root_safe(repo_root):
        raise ValueError(f"unsafe scratch root: {scratch_path}")
    resolved = path.resolve()
    scratch = scratch_path.resolve()
    try:
        resolved.relative_to(scratch)
    except ValueError as error:
        raise ValueError(f"audit output must be below {scratch}") from error
    if path.is_symlink():
        raise ValueError(f"audit output cannot be a symlink: {path}")
    return path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write JSON atomically under scratch")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path(__file__).resolve().parents[1]
    workspace = repo_root.parent
    try:
        report = audit(
            workspace,
            repo_root,
            EXPECTED_IFX,
            EXPECTED_IFX_VERSION,
            EXPECTED_IFX_SHA256,
        )
        if args.output:
            write_json(require_safe_output(args.output, workspace, repo_root), report)
        else:
            json.dump(report, sys.stdout, indent=2, sort_keys=True)
            sys.stdout.write("\n")
    except (OSError, ValueError) as error:
        print(f"intel integration audit configuration failure: {error}", file=sys.stderr)
        return 2
    return 0 if report["summary"]["status"] == "GO" else 3


if __name__ == "__main__":
    raise SystemExit(main())
