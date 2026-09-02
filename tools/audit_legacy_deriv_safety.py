#!/usr/bin/env python3
"""Fail-closed audit for the legacy KLAPS derived-cloud executable.

The audit deliberately does not infer source-to-binary provenance from matching
timestamps or embedded filenames.  It checks source, selection, configuration,
binary calls, and ifx settings, then keeps production provenance BLOCKED until
an independent build/runtime trace verifier exists.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


SCHEMA = "cloud-bal-legacy-deriv-safety-v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _strip_inline_comment(text: str) -> str:
    # These legacy statements contain no character literal with an exclamation
    # mark.  Rejecting unusual syntax is safer than attempting a Fortran parser.
    return text.split("!", 1)[0]


def fixed_form_statements(text: str) -> list[tuple[int, str]]:
    """Return conservative fixed-form statements with their first line."""
    statements: list[tuple[int, str]] = []
    current = ""
    current_line = 0

    def flush() -> None:
        nonlocal current, current_line
        if current.strip():
            statements.append((current_line, current.strip()))
        current = ""
        current_line = 0

    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip():
            continue
        if raw[0] in "cC*!" or raw.lstrip().startswith("!"):
            continue
        continuation = len(raw) >= 6 and raw[5] not in (" ", "0")
        code = raw[6:] if len(raw) >= 7 else raw
        code = _strip_inline_comment(code).strip()
        if not code:
            continue
        if continuation and current:
            current += " " + code
        else:
            flush()
            current = code
            current_line = line_number
    flush()
    return statements


def _compact(statement: str) -> str:
    return re.sub(r"\s+", "", statement.lower())


def _rstrip_line(text: str) -> str:
    if text.endswith("\r\n"):
        ending = "\r\n"
    elif text.endswith("\n"):
        ending = "\n"
    else:
        ending = ""
    content = text[: -len(ending)] if ending else text
    return content.rstrip() + ending


def _condition_is_constant_false(condition: str) -> bool:
    compact = _compact(condition)
    # Accept only the two forms produced by the safety patch.  A general
    # expression containing FALSE (for example MERGE(.FALSE.,...)) is not proof.
    while compact.startswith("(") and compact.endswith(")"):
        compact = compact[1:-1]
    return compact in {
        ".false.",
        ".false..and.l_evap_radar",
        "l_evap_radar.and..false.",
    }


def _laps_deriv_subroutine(text: str) -> list[tuple[int, str]]:
    selected: list[tuple[int, str]] = []
    inside = False
    for line, statement in fixed_form_statements(text):
        compact = _compact(statement)
        if not inside and re.match(r"^subroutinelaps_deriv_sub(?:\(|$)", compact):
            inside = True
        if inside:
            selected.append((line, statement))
            if compact == "end" or compact.startswith("endsubroutinelaps_deriv_sub"):
                return selected
    return []


def _call_arguments(statement: str, procedure: str) -> list[str]:
    match = re.search(
        rf"\bcall\s+{re.escape(procedure)}\s*\((.*)\)\s*$",
        statement,
        re.IGNORECASE,
    )
    if not match:
        return []
    arguments: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    body = match.group(1)
    index = 0
    while index < len(body):
        character = body[index]
        starts_token = index == 0 or not (
            body[index - 1].isalnum() or body[index - 1] == "_"
        )
        if (
            quote is None
            and character.isdigit()
            and starts_token
            and re.match(r"\d(?:\s*\d)*\s*[hH]", body[index:])
        ):
            return []
        current.append(character)
        if quote:
            if character == quote:
                if index + 1 < len(body) and body[index + 1] == quote:
                    index += 1
                    current.append(body[index])
                else:
                    quote = None
        elif character in "'\"":
            quote = character
        elif character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
            if depth < 0:
                return []
        elif character == "," and depth == 0:
            current.pop()
            arguments.append("".join(current).strip())
            current = []
        index += 1
    if quote or depth != 0:
        return []
    arguments.append("".join(current).strip())
    return arguments if all(arguments) else []


def analyze_source(text: str) -> dict[str, Any]:
    statements = _laps_deriv_subroutine(text)
    stack: list[dict[str, Any]] = []
    frames: dict[int, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    radar_calls: list[dict[str, Any]] = []
    next_frame = 1

    for line, statement in statements:
        compact = _compact(statement)
        if re.match(r"^end\s*if\b", statement, re.IGNORECASE) or compact == "endif":
            if stack:
                frame = stack.pop()
                frames[frame["id"]]["closed"] = True
            continue
        else_if = re.match(
            r"^else\s*if\s*\((.*)\)\s*then\s*$", statement, re.IGNORECASE
        ) or re.match(r"^elseif\s*\((.*)\)\s*then\s*$", statement, re.IGNORECASE)
        if else_if:
            if stack:
                stack[-1]["branch_false"] = _condition_is_constant_false(
                    else_if.group(1)
                )
            continue
        if re.match(r"^else\b", statement, re.IGNORECASE):
            if stack:
                stack[-1]["branch_false"] = False
            continue

        block_if = re.match(r"^if\s*\((.*)\)\s*then\s*$", statement, re.IGNORECASE)
        single_if = re.match(
            r"^if\s*\((.*)\)\s*call\s+(rfill_evap|get_radar_deriv)\b",
            statement,
            re.IGNORECASE,
        )
        if single_if:
            record = {
                "line": line,
                "single_statement_guard": _condition_is_constant_false(
                    single_if.group(1)
                ),
                "guard_frames": [],
            }
            (calls if single_if.group(2).lower() == "rfill_evap" else radar_calls).append(
                record
            )
            continue
        if block_if:
            frame = {
                "id": next_frame,
                "line": line,
                "branch_false": _condition_is_constant_false(block_if.group(1)),
            }
            frames[next_frame] = {"closed": False}
            next_frame += 1
            stack.append(frame)
            continue
        if re.search(r"\bcall\s+rfill_evap\b", statement, re.IGNORECASE):
            calls.append(
                {
                    "line": line,
                    "single_statement_guard": False,
                    "guard_frames": [
                        (frame["id"], frame["branch_false"]) for frame in stack
                    ],
                }
            )
        if re.search(r"\bcall\s+get_radar_deriv\b", statement, re.IGNORECASE):
            radar_calls.append(
                {
                    "line": line,
                    "single_statement_guard": False,
                    "guard_frames": [
                        (frame["id"], frame["branch_false"]) for frame in stack
                    ],
                }
            )
    for call in calls + radar_calls:
        block_guard = any(
            branch_false and frames.get(frame_id, {}).get("closed", False)
            for frame_id, branch_false in call.pop("guard_frames")
        )
        call["constant_false_guard"] = call.pop("single_statement_guard") or block_guard

    cloud_calls = [
        (line, statement)
        for line, statement in statements
        if re.search(r"\bcall\s+get_cloud_deriv\b", statement, re.IGNORECASE)
    ]
    cloud_arguments = (
        _call_arguments(cloud_calls[0][1], "get_cloud_deriv")
        if len(cloud_calls) == 1
        else []
    )
    cloud_bogus_w_argument = cloud_arguments[26] if len(cloud_arguments) == 29 else None
    cloud_compile_time_off = (
        cloud_bogus_w_argument is not None
        and _compact(cloud_bogus_w_argument) == ".false."
    )
    cloud_call_line = cloud_calls[0][0] if len(cloud_calls) == 1 else 0
    cloud_output_initialized = any(
        line < cloud_call_line
        and _compact(statement) in {"w_3d=0.", "w_3d=r_missing_data"}
        for line, statement in statements
    )
    cloud_output_not_normal = not any(
        _compact(statement) == "j_status(n_lco)=ss_normal"
        for _, statement in statements
    )
    source_compile_time_off = bool(statements) and (
        not calls or all(item["constant_false_guard"] for item in calls)
    )
    radar_compile_time_off = bool(statements) and (
        not radar_calls
        or all(item["constant_false_guard"] for item in radar_calls)
    )
    return {
        "laps_deriv_subroutine_found": bool(statements),
        "rfill_evap_calls": calls,
        "rfill_evap_call_count": len(calls),
        "evaporation_compile_time_off": source_compile_time_off,
        "get_radar_deriv_calls": radar_calls,
        "radar_bogus_w_compile_time_off": radar_compile_time_off,
        "cloud_bogus_w_authority": (
            "DISABLED_AT_CALL_SITE"
            if cloud_compile_time_off
            else "NOT_LITERAL_FALSE"
        ),
        "get_cloud_deriv_call_count": len(cloud_calls),
        "cloud_bogus_w_call_argument": cloud_bogus_w_argument,
        "cloud_bogus_w_compile_time_off": cloud_compile_time_off,
        "cloud_output_initialized": cloud_output_initialized,
        "cloud_output_not_normal": cloud_output_not_normal,
    }


def source_is_safe(source_info: dict[str, Any]) -> bool:
    """Require literal safety at each physical call site."""
    return all(
        (
            source_info["evaporation_compile_time_off"],
            source_info["radar_bogus_w_compile_time_off"],
            source_info["cloud_bogus_w_compile_time_off"],
            source_info["cloud_output_initialized"],
            source_info["cloud_output_not_normal"],
        )
    )


def parse_deriv_namelist(text: str) -> dict[str, Any]:
    kept: list[str] = []
    for raw in text.splitlines():
        if raw and raw[0] in "cC*!":
            continue
        kept.append(_strip_inline_comment(raw))
    content = "\n".join(kept)
    mode_matches = re.findall(
        r"\bmode_evap\s*=\s*([+-]?\d+)", content, re.IGNORECASE
    )
    radar_matches = re.findall(
        r"\bl_bogus_radar_w\s*=\s*\.(true|false)\.", content, re.IGNORECASE
    )
    return {
        "mode_evap": int(mode_matches[0]) if len(mode_matches) == 1 else None,
        "mode_evap_occurrences": len(mode_matches),
        "l_bogus_radar_w": (
            radar_matches[0].lower() == "true" if len(radar_matches) == 1 else None
        ),
        "l_bogus_radar_w_occurrences": len(radar_matches),
    }


def parse_makefile(
    makefile_text: str, source: Path, makefile_path: Path | None = None
) -> dict[str, Any]:
    uncommented = "\n".join(line.split("#", 1)[0] for line in makefile_text.splitlines())
    logical = re.sub(r"\\\s*\n", " ", uncommented)
    src_matches = re.findall(r"(?mi)^\s*SRC\s*=\s*(.+)$", logical)
    exe_matches = re.findall(r"(?mi)^\s*EXE\s*=\s*([^\s#]+)", logical)
    tokens = src_matches[0].split() if len(src_matches) == 1 else []
    matching_tokens = [token for token in tokens if token == source.name]
    path_matches = True
    if makefile_path is not None and len(matching_tokens) == 1:
        path_matches = (makefile_path.parent / matching_tokens[0]).resolve() == source.resolve()
    selected = len(matching_tokens) == 1 and path_matches
    return {
        "source_list_found": len(src_matches) == 1,
        "source_selected_once": selected,
        "selected_source_path_matches": path_matches,
        "source_token": source.name,
        "executable_name": exe_matches[0] if len(exe_matches) == 1 else None,
    }


def parse_make_config(text: str) -> dict[str, Any]:
    uncommented = "\n".join(line.split("#", 1)[0] for line in text.splitlines())
    fc_matches = re.findall(r"(?mi)^\s*FC\s*=\s*([^\s#]+)", uncommented)
    cpp_matches = re.findall(r"(?mi)^\s*CPP\s*=\s*([^\s#]+)", uncommented)
    selected = fc_matches[0] if len(fc_matches) == 1 else None
    cpp = cpp_matches[0] if len(cpp_matches) == 1 else None
    return {
        "fortran_compiler_setting": selected,
        "preprocessor_setting": cpp,
        "ifx_selected": (
            selected is not None
            and cpp is not None
            and Path(selected).name == "ifx"
            and Path(cpp).name == "ifx"
        ),
    }


def job_selects_binary(job_text: str, executable_name: str | None) -> bool:
    if not executable_name:
        return False
    uncommented = "\n".join(line.split("#", 1)[0] for line in job_text.splitlines())
    matches = re.findall(
        rf"(?<![A-Za-z0-9_.-]){re.escape(executable_name)}\b", uncommented
    )
    return len(matches) == 1


def binary_call_edge(binary: Path) -> dict[str, Any]:
    result = {
        "auditable": False,
        "caller_symbol": None,
        "direct_rfill_evap_call": None,
        "direct_get_radar_deriv_call": None,
        "detail": "objdump/nm evidence unavailable",
    }
    try:
        nm = subprocess.run(
            ["nm", "-a", os.fspath(binary)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return result
    symbols = re.findall(r"\b(laps_deriv_sub_*)$", nm.stdout, re.MULTILINE)
    if len(symbols) != 1:
        result["detail"] = f"expected one laps_deriv_sub symbol, found {len(symbols)}"
        return result
    caller = symbols[0]
    try:
        dump = subprocess.run(
            ["objdump", "-dr", os.fspath(binary)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return result
    caller_present = bool(re.search(rf"<{re.escape(caller)}>:\s*$", dump.stdout, re.MULTILINE))
    evap_matches = re.findall(
        r"\b(?:callq?|bl)\b[^\n]*<rfill_evap_*(?:@plt)?>",
        dump.stdout,
        re.IGNORECASE,
    )
    radar_matches = re.findall(
        r"\b(?:callq?|bl)\b[^\n]*<get_radar_deriv_*(?:@plt)?>",
        dump.stdout,
        re.IGNORECASE,
    )
    if not caller_present:
        result["detail"] = "objdump did not emit the audited caller"
        return result
    direct = bool(evap_matches)
    radar_direct = bool(radar_matches)
    result.update(
        {
            "auditable": True,
            "caller_symbol": caller,
            "direct_rfill_evap_call": direct,
            "direct_get_radar_deriv_call": radar_direct,
            "detail": (
                f"rfill={len(evap_matches)}, get_radar_deriv={len(radar_matches)} "
                "direct call(s) in binary"
            ),
        }
    )
    return result


def render_safety_patch(text: str, label: str) -> str:
    """Return the minimal deterministic fail-closed patch for legacy source."""
    lines = text.splitlines(keepends=True)
    mode_hits = [
        index
        for index, line in enumerate(lines)
        if _compact(_strip_inline_comment(line))
        == "if(mode_evap.gt.0)l_evap_radar=.true."
    ]
    cloud_hits = [
        index
        for index, line in enumerate(lines)
        if _compact(_strip_inline_comment(line)) == "l_flag_bogus_w=.true."
    ]
    evap_if_hits = [
        index
        for index, line in enumerate(lines)
        if _compact(_strip_inline_comment(line)) == "if(l_evap_radar)then"
    ]
    radar_if_hits = [
        index
        for index, line in enumerate(lines)
        if _compact(_strip_inline_comment(line))
        == "if(l_flag_bogus_w.and.l_bogus_radar_w)then"
    ]
    cloud_argument_hits = [
        index
        for index, line in enumerate(lines)
        if re.search(
            r"\bl_flag_bogus_w\s*,\s*w_3d\s*,\s*istatus\s*\)",
            _strip_inline_comment(line),
            re.IGNORECASE,
        )
    ]
    lco_normal_hits = [
        index
        for index, line in enumerate(lines)
        if _compact(_strip_inline_comment(line)) == "j_status(n_lco)=ss_normal"
    ]

    analysis = analyze_source(text)
    if source_is_safe(analysis):
        return ""
    if (
        len(mode_hits) != 1
        or len(cloud_hits) != 1
        or len(evap_if_hits) != 1
        or len(radar_if_hits) != 1
        or len(cloud_argument_hits) != 1
        or len(lco_normal_hits) > 1
    ):
        raise ValueError(
            "unsupported source layout: expected one legacy evaporation assignment, "
            "one cloud bogus-w assignment and argument, one evaporation IF, and one "
            "radar bogus-w IF"
        )

    newline = "\r\n" if lines[mode_hits[0]].endswith("\r\n") else "\n"
    indent = re.match(r"^\s*", lines[mode_hits[0]]).group(0)
    safety = [
        f"{indent}! Cloud-BAL fail-closed production safety gate.{newline}",
        f"{indent}l_evap_radar = .false.{newline}",
        f"{indent}mode_evap = 0{newline}",
        f"{indent}l_bogus_radar_w = .false.{newline}",
    ]
    lines[mode_hits[0] : mode_hits[0] + 1] = safety

    call_start = next(
        (
            index
            for index, line in enumerate(lines)
            if re.search(
                r"\bcall\s+get_cloud_deriv\b",
                _strip_inline_comment(line),
                re.IGNORECASE,
            )
        ),
        None,
    )
    if call_start is None:
        raise ValueError("unsupported source layout: cloud call start is absent")
    cloud_indent = re.match(r"^\s*", lines[call_start]).group(0)
    lines.insert(call_start, f"{cloud_indent}w_3d = r_missing_data{newline}")

    # Indices after the replacement moved by three lines; locate them again.
    for index, line in enumerate(lines):
        if _compact(_strip_inline_comment(line)) == "l_flag_bogus_w=.true.":
            lines[index] = _rstrip_line(
                re.sub(r"\.true\.", ".false.", line, count=1, flags=re.IGNORECASE)
            )
        if _compact(_strip_inline_comment(line)) == "if(l_evap_radar)then":
            lines[index] = _rstrip_line(
                re.sub(
                    r"if\s*\(\s*l_evap_radar\s*\)\s*then",
                    "if(.false. .and. l_evap_radar)then",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
        if re.search(
            r"\bl_flag_bogus_w\s*,\s*w_3d\s*,\s*istatus\s*\)",
            _strip_inline_comment(line),
            re.IGNORECASE,
        ):
            lines[index] = _rstrip_line(
                re.sub(
                    r"\bl_flag_bogus_w\b",
                    ".false.",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
        if (
            _compact(_strip_inline_comment(line))
            == "if(l_flag_bogus_w.and.l_bogus_radar_w)then"
        ):
            lines[index] = _rstrip_line(
                re.sub(
                    r"if\s*\(\s*l_flag_bogus_w\s*\.and\.\s*l_bogus_radar_w\s*\)\s*then",
                    "if(.false.)then",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
        if _compact(_strip_inline_comment(line)) == "j_status(n_lco)=ss_normal":
            lines[index] = _rstrip_line(
                re.sub(
                    r"\bss_normal\b",
                    "sys_no_data",
                    line,
                    count=1,
                    flags=re.IGNORECASE,
                )
            )
    patched = "".join(lines)
    patched_analysis = analyze_source(patched)
    if not source_is_safe(patched_analysis):
        raise ValueError("generated patch did not satisfy source safety contract")
    return "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{label}",
            tofile=f"b/{label}",
        )
    )


def _input_record(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return {"path": os.fspath(path.resolve()), "sha256": sha256_file(path)}


def run_audit(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source.resolve()
    source_info = analyze_source(source.read_text(encoding="utf-8"))
    make_info = (
        parse_makefile(args.makefile.read_text(encoding="utf-8"), source, args.makefile)
        if args.makefile
        else None
    )
    make_config_info = (
        parse_make_config(args.make_config.read_text(encoding="utf-8"))
        if args.make_config
        else None
    )
    namelist_info = (
        parse_deriv_namelist(args.namelist.read_text(encoding="utf-8"))
        if args.namelist
        else None
    )
    binary_info = binary_call_edge(args.binary) if args.binary else None
    job_selected = bool(
        args.job_script
        and make_info
        and job_selects_binary(
            args.job_script.read_text(encoding="utf-8"), make_info["executable_name"]
        )
    )

    source_safe = source_is_safe(source_info)
    selection_safe = bool(
        make_info and make_info["source_selected_once"] and job_selected
    )
    configuration_safe = bool(
        namelist_info
        and namelist_info["mode_evap"] == 0
        and namelist_info["l_bogus_radar_w"] is False
    )
    binary_safe = bool(
        binary_info
        and binary_info["auditable"]
        and binary_info["direct_rfill_evap_call"] is False
        and binary_info["direct_get_radar_deriv_call"] is False
    )
    toolchain_safe = bool(make_config_info and make_config_info["ifx_selected"])

    stages = {
        "source_authority": {
            "status": "PASS" if source_safe else "BLOCKED",
            "evidence": source_info,
        },
        "build_and_job_selection": {
            "status": "PASS" if selection_safe else "BLOCKED",
            "evidence": {"makefile": make_info, "job_binary_name_selected": job_selected},
        },
        "namelist_defense": {
            "status": "PASS" if configuration_safe else "BLOCKED",
            "evidence": namelist_info,
        },
        "binary_legacy_calls": {
            "status": "PASS" if binary_safe else "BLOCKED",
            "evidence": binary_info,
        },
        "ifx_configuration": {
            "status": "PASS" if toolchain_safe else "BLOCKED",
            "evidence": make_config_info,
        },
        "production_provenance": {
            "status": "BLOCKED",
            "evidence": (
                "No independent clean-build execution trace binds source to binary, "
                "and no runtime argv/environment trace resolves KL05EXET."
            ),
        },
    }
    blocked = sorted(name for name, stage in stages.items() if stage["status"] == "BLOCKED")
    return {
        "schema": SCHEMA,
        "status": "BLOCKED" if blocked else "GO",
        "blocked_stages": blocked,
        "contract_note": (
            "Namelist-only OFF is never sufficient. Production remains BLOCKED "
            "until a trusted build/runtime trace closes production_provenance."
        ),
        "inputs": {
            key: _input_record(path)
            for key, path in {
                "source": args.source,
                "makefile": args.makefile,
                "make_config": args.make_config,
                "job_script": args.job_script,
                "namelist": args.namelist,
                "binary": args.binary,
            }.items()
        },
        "stages": stages,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--makefile", type=Path)
    parser.add_argument("--make-config", type=Path)
    parser.add_argument("--job-script", type=Path)
    parser.add_argument("--namelist", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path, help="write JSON here; stdout otherwise")
    parser.add_argument("--emit-patch", type=Path, help="write a review-only patch")
    parser.add_argument(
        "--patch-label", default="src/deriv/laps_deriv_sub.f", help="path shown in patch"
    )
    return parser


def write_new_file(path: Path, payload: str) -> None:
    """Write an audit artifact without ever replacing an existing path."""
    with path.open("x", encoding="utf-8") as stream:
        stream.write(payload)


def output_is_in_protected_original_tree(path: Path) -> bool:
    repo_root = Path(__file__).resolve().parents[1]
    workspace_root = repo_root.parent
    resolved = path.resolve()
    protected = (
        workspace_root / "ANAL",
        workspace_root / "MODL",
        workspace_root / "klaps-v5.0_",
    )
    return any(resolved == root.resolve() or root.resolve() in resolved.parents for root in protected)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    for name in (
        "source",
        "makefile",
        "make_config",
        "job_script",
        "namelist",
        "binary",
    ):
        path = getattr(args, name)
        if path is not None and not path.is_file():
            raise SystemExit(f"{name} is not a regular file: {path}")
    input_paths = {
        path.resolve()
        for name in (
            "source",
            "makefile",
            "make_config",
            "job_script",
            "namelist",
            "binary",
        )
        if (path := getattr(args, name)) is not None
    }
    output_paths = [path for path in (args.emit_patch, args.output) if path is not None]
    if len({path.resolve() for path in output_paths}) != len(output_paths):
        raise SystemExit("--emit-patch and --output must be different new files")
    for path in output_paths:
        if path.resolve() in input_paths:
            raise SystemExit(f"refusing to overwrite an audited input: {path}")
        if output_is_in_protected_original_tree(path):
            raise SystemExit(f"refusing to write inside protected original tree: {path}")
        if path.exists():
            raise SystemExit(f"refusing to replace an existing audit artifact: {path}")
    if args.emit_patch:
        patch = render_safety_patch(
            args.source.read_text(encoding="utf-8"),
            args.patch_label,
        )
        write_new_file(args.emit_patch, patch)
    report = run_audit(args)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        write_new_file(args.output, payload)
    else:
        sys.stdout.write(payload)
    return 0 if report["status"] == "GO" else 2


if __name__ == "__main__":
    raise SystemExit(main())
