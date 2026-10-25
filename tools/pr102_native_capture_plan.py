#!/usr/bin/env python3
"""Materialize an insertion-only PR98 capture overlay plan for the pinned C2 sources."""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

import pr98_prepare_native_capture as pr98


BASE_RECEIPT = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
BASE_RECEIPT_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
PR98_BUILD = Path("/var/tmp/pr98_native_capture_build_v4_20261022/pr87_native_overlay_build.json")
PR98_BUILD_SHA256 = "34a3b92a1d0288e172d34423a1f254ce371213b757f254c13c1c4f6727b7beb7"
PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
EXPECTED_EXE_SHA256 = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
PLAN_DIR = Path(__file__).resolve().parents[1] / "docs/evidence/pr102_execution_20261025/c2_capture_source_plan_v3"
BUILDER = "tools/pr87_build_native_overlay.py"
EXPECTED_PATTERN_COUNTS = {
    "advective_call_sites": 5,
    "pressure_gradient_call_sites": 1,
    "coriolis_call_sites": 2,
    "u_horizontal_diffusion_call_sites": 1,
    "v_horizontal_diffusion_call_sites": 1,
    "rk_tendency_subroutines": 1,
    "rk_addtend_dry_calls": 1,
    "advance_mu_t_calls": 1,
}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _only_insertions(before: str, after: str, label: str) -> dict:
    old_lines, new_lines = before.splitlines(), after.splitlines()
    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    opcodes = matcher.get_opcodes()
    whitespace_only_changes = 0
    for tag, i1, i2, j1, j2 in opcodes:
        if tag in {"equal", "insert"}:
            continue
        old = old_lines[i1:i2]
        new = new_lines[j1:j2]
        if tag == "delete" and all(not line.strip() for line in old):
            whitespace_only_changes += len(old)
            continue
        old_body = [line.strip() for line in old if line.strip()]
        new_body = [line.strip() for line in new if line.strip()]
        if tag == "replace" and (not old_body or _is_subsequence(old_body, new_body)):
            whitespace_only_changes += len(old)
            continue
        raise ValueError(f"{label} capture transform changed source body: {tag} {old_body!r} -> {new_body!r}")
    return {"original_lines": len(before.splitlines()),
            "preserved_lines": sum(i2-i1 for tag,i1,i2,_,_ in opcodes if tag == "equal"),
            "inserted_lines": sum(j2-j1 for tag,_,_,j1,j2 in opcodes if tag == "insert"),
            "whitespace_only_changes": whitespace_only_changes,
            "source_body_preserved": True}


def _is_subsequence(needles: list[str], values: list[str]) -> bool:
    position = 0
    for value in values:
        if position < len(needles) and value == needles[position]:
            position += 1
    return position == len(needles)


def _pr98_writer_tail(observer_source: bytes) -> tuple[str, dict]:
    text = observer_source.decode("utf-8")
    match = re.search(r"(?im)^SUBROUTINE\s+pr98_dump3\s*\(", text)
    if match is None:
        raise ValueError("PR98 combined observer lacks the writer-tail start anchor")
    tail = text[match.start():]
    procedure_names = re.findall(r"(?im)^SUBROUTINE\s+(pr98_dump\d)\s*\(", tail)
    end_names = re.findall(r"(?im)^END SUBROUTINE\s+(pr98_dump\d)\s*$", tail)
    expected = ["pr98_dump3", "pr98_dump2", "pr98_dump1", "pr98_dump0"]
    if procedure_names != expected or end_names != expected:
        raise ValueError("PR98 writer tail must contain exactly dump3, dump2, dump1, dump0")
    return tail, {
        "source_path_binding": "source_inputs.pr98_private_writer",
        "start_anchor": "SUBROUTINE pr98_dump3(",
        "start_line": text.count("\n", 0, match.start()) + 1,
        "start_byte": len(text[:match.start()].encode("utf-8")),
        "combined_source_sha256": sha256(observer_source),
        "prefix_sha256": sha256(text[:match.start()].encode("utf-8")),
        "tail_sha256": sha256(tail.encode("utf-8")),
        "procedure_names": procedure_names,
        "procedure_end_names": end_names,
        "procedure_count": len(procedure_names),
        "procedure_order": expected,
    }


def _anchor_counts(module: str, solve: str) -> dict:
    import re
    patterns = {
        "advective_call_sites": r"(?im)^\s*CALL\s+(?:advect_[uvw]|advect_weno_[uv])\s*\(",
        "pressure_gradient_call_sites": r"(?im)^\s*CALL\s+horizontal_pressure_gradient\s*\(",
        "coriolis_call_sites": r"(?im)^\s*CALL\s+(?:perturbation_coriolis|coriolis)\s*\(",
        "u_horizontal_diffusion_call_sites": r"(?im)^\s*CALL\s+horizontal_diffusion\s*\(\s*['\"]u['\"]",
        "v_horizontal_diffusion_call_sites": r"(?im)^\s*CALL\s+horizontal_diffusion\s*\(\s*['\"]v['\"]",
        "rk_tendency_subroutines": r"(?im)^\s*SUBROUTINE\s+rk_tendency\b",
    }
    counts = {name: len(re.findall(pattern, module)) for name, pattern in patterns.items()}
    counts["rk_addtend_dry_calls"] = len(re.findall(r"(?im)^\s*CALL\s+rk_addtend_dry\s*\(", solve))
    counts["advance_mu_t_calls"] = len(re.findall(r"(?im)^\s*CALL\s+advance_mu_t\s*\(", solve))
    if counts != EXPECTED_PATTERN_COUNTS:
        raise ValueError(f"C2 capture anchors drifted: {counts}")
    return counts


def make_plan(output_dir: Path, receipt_path: Path = BASE_RECEIPT,
              pr98_build_path: Path = PR98_BUILD) -> dict:
    if output_dir.exists():
        raise FileExistsError(f"refusing to replace capture source-plan directory: {output_dir}")
    base_bytes = receipt_path.read_bytes()
    if receipt_path == BASE_RECEIPT and sha256(base_bytes) != BASE_RECEIPT_SHA256:
        raise ValueError("pinned C2 base build receipt changed")
    base = json.loads(base_bytes)
    if (base.get("schema") != "pr87_native_overlay_build_v1" or
            base.get("status") != "PASS_OVERLAY_BUILD" or
            base.get("executable_sha256") != EXPECTED_EXE_SHA256):
        raise ValueError("base build is not the pinned C2 overlay")
    base_profile = Path(base["compiler_profile_path"])
    profile = Path(__file__).resolve().parents[1] / "tests/intel_toolchain.sh"
    if (sha256(profile.read_bytes()) != PROFILE_SHA256 or
            sha256(base_profile.read_bytes()) != PROFILE_SHA256 or
            base["compiler_profile_sha256"] != PROFILE_SHA256):
        raise ValueError("pinned Intel profile identity changed")
    pr98_bytes = pr98_build_path.read_bytes()
    if pr98_build_path == PR98_BUILD and sha256(pr98_bytes) != PR98_BUILD_SHA256:
        raise ValueError("pinned PR98 observer build receipt changed")
    capture_build = json.loads(pr98_bytes)
    observer = capture_build["extra_observer"]
    observer_source = Path(observer["requested_source_path"])
    observer_bytes = observer_source.read_bytes()
    if sha256(observer_bytes) != observer["requested_source_sha256"]:
        raise ValueError("private PR98 observer source changed")
    writer_tail, writer_tail_binding = _pr98_writer_tail(observer_bytes)

    overrides = base["source_overrides"]
    module_row, solve_row = overrides["module_em.o"], overrides["solve_em.o"]
    module_em_source_path = Path(module_row["requested_path"])
    solve_em_source_path = Path(solve_row["requested_path"])
    module_bytes, solve_bytes = module_em_source_path.read_bytes(), solve_em_source_path.read_bytes()
    if sha256(module_bytes) != module_row["requested_sha256"]:
        raise ValueError("C2 module_em source differs from its build receipt")
    if sha256(solve_bytes) != solve_row["requested_sha256"]:
        raise ValueError("C2 solve_em source differs from its build receipt")
    module, solve = module_bytes.decode("utf-8"), solve_bytes.decode("utf-8")
    anchors = _anchor_counts(module, solve)
    module_instrumented, solve_instrumented = pr98.transform(module, solve)
    module_instrumented += "\n" + writer_tail + "\n"
    body_proof = {
        "module_em": _only_insertions(module, module_instrumented, "module_em"),
        "solve_em": _only_insertions(solve, solve_instrumented, "solve_em"),
    }

    output_dir.mkdir(parents=True)
    module_out, solve_out = output_dir / "module_em.F", output_dir / "solve_em.F"
    module_out.write_text(module_instrumented)
    solve_out.write_text(solve_instrumented)
    patch_text = "".join(difflib.unified_diff(
        module.splitlines(keepends=True), module_instrumented.splitlines(keepends=True),
        fromfile=str(module_em_source_path), tofile="PR102/module_em.F"))
    patch_text += "".join(difflib.unified_diff(
        solve.splitlines(keepends=True), solve_instrumented.splitlines(keepends=True),
        fromfile=str(solve_em_source_path), tofile="PR102/solve_em.F"))
    patch_path = output_dir / "source_only_insertions.patch"
    patch_path.write_text(patch_text)

    object_rows = {row["member"]: row for row in base["compiled_overrides"]}
    changed_members = ("module_em.o", "solve_em.o")
    source_overrides = {member: str((module_out if member == "module_em.o" else solve_out
                                     if member == "solve_em.o" else Path(row["requested_path"])).resolve())
                        for member, row in overrides.items()}
    remaps = {}
    for member in changed_members:
        row = next(item for item in base["compiled_overrides"] if item["member"] == member)
        source_override = source_overrides[member]
        preprocessor_argv = [source_override if arg == row["source_path"] else arg
                             for arg in row["preprocess_argv"]]
        compile_argv = [arg.replace("/var/tmp/pr99_bulk_candidate_native_c2_20261022",
                                   "<scratch>") for arg in row["compile_argv"]]
        preprocessor_argv = [arg.replace("/var/tmp/pr99_bulk_candidate_native_c2_20261022",
                                        "<scratch>") for arg in preprocessor_argv]
        remaps[member] = {
            "base_source_sha256": row["source_sha256"],
            "base_preprocessed_sha256": row["generated_source_sha256"],
            "base_object_sha256": row["object_sha256"],
            "preprocess_argv_from_receipt": preprocessor_argv,
            "compile_argv_from_receipt": compile_argv,
            "stdout_redirect": f"<scratch>/preprocessed/{member.removesuffix('.o')}.f90",
            "compile_input_rewrite": f"<scratch>/preprocessed/{member.removesuffix('.o')}.f90",
            "compile_output_rewrite": f"<scratch>/compile/{member}",
            "source_rewrite": source_override,
        }
    module_pins = []
    for row in base.get("modules", []):
        interface_path = Path(row["path"])
        if sha256(interface_path.read_bytes()) != row["sha256"]:
            raise ValueError(f"C2 module/interface changed: {interface_path}")
        module_pins.append({"path": str(interface_path), "sha256": row["sha256"],
                            "parent_path": row.get("parent_path"),
                            "parent_sha256": row.get("parent_sha256"),
                            "staged_sha256": row.get("staged_sha256"),
                            "regenerated": row.get("regenerated")})
    staged_link_pins = []
    for row in base.get("staged_link_inputs", {}).values():
        staged_path = Path(row["path"])
        if sha256(staged_path.read_bytes()) != row["sha256"]:
            raise ValueError(f"C2 staged link input changed: {staged_path}")
        staged_link_pins.append(row)
    inherited_library_pins = []
    for arg in base["link_argv"]:
        path = Path(arg)
        if path.is_file() and path.suffix in {".a", ".o"} and str(path) != base["archive_command"][2]:
            inherited_library_pins.append({"path": str(path), "sha256": sha256(path.read_bytes())})
    plan = {
        "schema": "pr102_native_source_capture_build_plan_v1",
        "status": "SOURCE_ONLY_PLAN_READY_FOR_ROOT_REVIEW_NO_BUILD",
        "launch_authorized": False,
        "plan_generator": {"path": str(Path(__file__).resolve()),
                           "sha256": sha256(Path(__file__).read_bytes())},
        "base_c2_receipt": {"path": str(receipt_path), "sha256": sha256(base_bytes)},
        "base_c2_executable_sha256": base["executable_sha256"],
        "base_c2_archive_sha256": base["archive_sha256"],
        "intel_profile": {"path": str(profile), "sha256": PROFILE_SHA256,
                           "compiler_path": base["compiler_path"],
                           "compiler_sha256": base["compiler_sha256"],
                           "compiler_version": base["compiler_version"]},
        "source_inputs": {
            "module_em": {"path": str(module_em_source_path), "sha256": sha256(module_bytes),
                          "transformed_path": str(module_out), "transformed_sha256": sha256(module_instrumented.encode())},
            "solve_em": {"path": str(solve_em_source_path), "sha256": sha256(solve_bytes),
                         "transformed_path": str(solve_out), "transformed_sha256": sha256(solve_instrumented.encode())},
            "pr98_private_writer": {"path": str(observer_source), "sha256": sha256(observer_bytes),
                                    "embedded_in": "transformed module_em.F"},
        },
        "pr98_writer_tail": writer_tail_binding,
        "anchors": anchors,
        "source_body_proof": body_proof,
        "source_diff": {"path": str(patch_path), "sha256": sha256(patch_path.read_bytes()),
                        "changed_compiled_members": list(changed_members)},
        "compiled_object_expectations": {
            "only_source_modified_members": list(changed_members),
            "base_object_hashes": {name: object_rows[name]["object_sha256"] for name in object_rows},
            "unchanged_overrides_reused_byte_exact": [name for name in object_rows if name not in changed_members],
            "base_extra_observer_preserved": base["extra_observer"],
            "base_archive_members_replaced": list(changed_members),
            "all_other_archive_member_bytes_must_match": True,
            "parent_archive_and_link_argv_pinned": True,
        },
        "inherited_c2_inputs": {
            "base_archive": {"path": base["archive_command"][2], "sha256": base["archive_sha256"]},
            "staged_link_inputs": staged_link_pins,
            "inherited_object_libraries": inherited_library_pins,
            "c2_modules_and_interfaces": module_pins,
            "staged_parent_modules": base.get("staged_parent_modules", []),
        },
        "build_command_plan": {
            "scratch": "/var/tmp/pr102_c2_native_capture_20261025_<unique>",
            "fresh_scratch_required": True,
            "cwd": "fresh scratch build root; maintained source tree is read-only",
            "builder": "custom C2 receipt-bound build plan required; tools/pr87_build_native_overlay.py is C1-parent-pinned and must not be called for this C2 plan",
            "steps": [
                "source Cloud-BAL/tests/intel_toolchain.sh and verify its pinned ifx/profile identities",
                "copy exact C2 compile-module inputs and exact C2 base archive into fresh scratch; verify every staged hash",
                "run the recorded C2 preprocess argv for module_em.o and solve_em.o with only source/output paths remapped to scratch",
                "run the recorded C2 ifx compile argv for only module_em.o and solve_em.o with only source/output paths remapped to scratch",
                "copy the exact C2 base archive and replace only module_em.o and solve_em.o with the two new objects",
                "compare every other archive member byte-for-byte to the C2 base archive",
                "link with the receipt-pinned C2 link argv, changing only output executable and copied archive paths",
                "compare all source override object hashes, inherited archive members, staged link inputs, and inherited module/interface hashes; only the two replacements may differ",
            ],
            "changed_member_commands": remaps,
            "source_override_members": list(source_overrides),
            "archive_replacement_argv_template": ["ar", "r", "<scratch>/link/main/libwrflib_pr87_overlay.a",
                                                  "<scratch>/compile/module_em.o", "<scratch>/compile/solve_em.o"],
            "link_argv_from_receipt": [arg.replace(base["archive_command"][2], "<scratch>/link/main/libwrflib_pr87_overlay.a")
                                       .replace(base["executable_path"], "<scratch>/wrf_pr87_capture.exe")
                                       for arg in base["link_argv"]],
            "base_link_argv_sha256": sha256(json.dumps(base["link_argv"], separators=(",", ":")).encode()),
        },
        "cohort_plan": [
            {"input": "HYDRO", "duration_seconds": 20, "expected_steps": 1},
            {"input": "original_p", "duration_seconds": 20, "expected_steps": 1},
            {"input": "candidate", "duration_seconds": 20, "expected_steps": 1},
        ],
        "capture_contract": {
            "pr98_builder": str(Path(pr98.__file__).resolve()),
            "pr98_builder_sha256": sha256(Path(pr98.__file__).read_bytes()),
            "capture_writer_record_bytes": "Fortran stream REAL32 arrays with recorded bounds; source compile uses -convert big_endian",
            "required_source_families": ["full dynamics RU/RV", "assembled RU/RV in/out", "MUDF", "MU before/after", "operator tendency in/out"],
            "writer_procedures_added_to_module_em": writer_tail_binding["procedure_names"],
            "existing_c2_extra_observer_source_and_object_reused_byte_exact": True,
            "scope_limit": "MUDF is combined DMDT+MU_TEND; this is not complete dry-mass flux closure.",
        },
    }
    return plan


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PLAN_DIR)
    args = parser.parse_args()
    plan = make_plan(args.output_dir)
    plan_path = args.output_dir / "build_plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": plan["status"], "plan": str(plan_path),
                      "source_diff_sha256": plan["source_diff"]["sha256"],
                      "changed_members": plan["compiled_object_expectations"]["only_source_modified_members"]}, indent=2))


if __name__ == "__main__":
    main()
