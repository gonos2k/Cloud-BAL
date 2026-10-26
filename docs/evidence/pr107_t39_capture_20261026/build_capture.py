#!/usr/bin/env python3
"""Build one receipt-bound module_em diagnostic object on the pinned C2 host."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import pr87_build_native_overlay as overlay

BASE_RECEIPT = Path("/var/tmp/pr99_bulk_candidate_native_c2_20261022/pr87_native_overlay_build.json")
BASE_RECEIPT_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
BASE_SOURCE_SHA256 = "d82efa15ee1c0a44080a8ef40b8a8aef436661f2093b6f66bef7e666584aa296"
PROFILE_SHA256 = "5439fa3a692acc9ee63571ee8dd8ff1ce50d1810e9339d9ead906f3c817111b4"
MEMBER = "module_em.o"
PROOF_SCHEMA = "pr107_t39_source_transform_proof_v1"
SOURCE_GENERATOR = ROOT / "docs/evidence/pr107_t39_capture_20261026/prepare_source.py"
HELPERS = {
    "pr92_diffusion_producer_capture.py",
    "pr99_group_failure_trace.py",
}
ALLOWED_REPLACEMENTS = [
    {"before": "group_failure_enabled=itimestep==32",
     "after": "group_failure_enabled=itimestep==39 .AND. rk==2"},
    {"before": "IF (.NOT.feasible .AND. itimestep==32 .AND. pr99_cell>0)",
     "after": "IF (.NOT.feasible .AND. itimestep==39 .AND. rk==2 .AND. pr99_cell>0)"},
    {"before": "IF (itimestep==32 .AND. pr99_cell>0)",
     "after": "IF (itimestep==39 .AND. rk==2 .AND. pr99_cell>0)"},
    {"before": "   INTEGER,PARAMETER :: pr92_targets(3,12)=RESHAPE([ &\n"
                "       127,5,22, &\n       170,42,23, &\n       171,43,23, &\n"
                "       163,44,20, &\n       158,47,20, &\n       232,203,20, &\n"
                "       203,213,21, &\n       11,216,21, &\n       2,218,13, &\n"
                "       22,228,21, &\n       41,229,14, &\n       43,239,19], [3,12])\n",
     "after": "   INTEGER,PARAMETER :: pr92_targets(3,1)=RESHAPE([ &\n"
               "       2,219,13], [3,1])\n"},
    {"before": "IF (all_pair_diffusion_identity(1)==15) THEN",
     "after": "IF (all_pair_diffusion_identity(1)==39.AND.rk_step==1) THEN"},
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_hash(path: Path, expected: str, label: str) -> None:
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"{label} hash mismatch: {path}")


def verify_source_transform(source: Path, proof: dict, base_source: Path) -> None:
    if proof.get("allowed_replacements") != ALLOWED_REPLACEMENTS:
        raise ValueError("source proof allowed replacements differ from the reviewed T39 scope")
    base_text = base_source.read_text(encoding="utf-8")
    expected_text = base_text
    for replacement in ALLOWED_REPLACEMENTS:
        before, after = replacement["before"], replacement["after"]
        if expected_text.count(before) != 1:
            raise ValueError(f"source anchor is not unique: {before[:80]!r}")
        expected_text = expected_text.replace(before, after, 1)
    if source.read_text(encoding="utf-8") != expected_text:
        raise ValueError("edited source contains changes outside the exact diagnostic allowlist")
    require_hash(SOURCE_GENERATOR, proof["generator_sha256"], "source generator")


def load_inputs(source: Path, proof_path: Path) -> tuple[dict, dict, dict]:
    receipt_bytes = BASE_RECEIPT.read_bytes()
    if hashlib.sha256(receipt_bytes).hexdigest() != BASE_RECEIPT_SHA256:
        raise ValueError("pinned C2 build receipt changed")
    base = json.loads(receipt_bytes)
    if (base.get("schema") != "pr87_native_overlay_build_v1" or
            base.get("status") != "PASS_OVERLAY_BUILD" or
            base.get("full_clean_build") is not False):
        raise ValueError("base is not the pinned partial-host C2 overlay")
    proof = json.loads(proof_path.read_text())
    if (proof.get("schema") != PROOF_SCHEMA or
            proof.get("base_source_sha256") != BASE_SOURCE_SHA256 or
            proof.get("edited_source_sha256") != sha256(source) or
            proof.get("math_source_unchanged") is not True or
            proof.get("changed_compiled_members") != [MEMBER] or
            proof.get("producer_target") != {"timestep": 39, "rkstep": 1,
                                              "cell_ijk": [2, 219, 13]} or
            proof.get("group_target") != {"timestep": 39, "rkstep": 2}):
        raise ValueError("source proof is absent, stale, or outside the one-object diagnostic scope")
    diff_path = Path(proof["diff_path"])
    require_hash(diff_path, proof["diff_sha256"], "source diff")
    helper_rows = proof.get("helpers", [])
    if (len(helper_rows) != len(HELPERS) or
            {Path(row["path"]).name for row in helper_rows} != HELPERS):
        raise ValueError("source proof does not bind the producer and grouped-capture helpers")
    for row in helper_rows:
        helper_path = Path(row["path"]).resolve()
        if helper_path.parent != (ROOT / "tools").resolve():
            raise ValueError(f"unexpected source transform helper path: {helper_path}")
        require_hash(helper_path, row["sha256"], "source transform helper")
    profile = Path(base["compiler_profile_path"])
    require_hash(profile, PROFILE_SHA256, "pinned Intel profile")
    require_hash(Path(base["compiler_path"]), base["compiler_sha256"], "pinned compiler")
    require_hash(Path(base["archive_command"][2]), base["archive_sha256"], "base C2 archive")
    require_hash(Path(base["executable_path"]), base["executable_sha256"], "base C2 executable")
    if hashlib.sha256(receipt_bytes).hexdigest() != BASE_RECEIPT_SHA256:
        raise ValueError("pinned C2 build receipt changed during validation")
    rows = {row["member"]: row for row in base["compiled_overrides"]}
    row = rows[MEMBER]
    if Path(proof["base_source_path"]).resolve() != Path(row["source_path"]).resolve():
        raise ValueError("source proof base path differs from the pinned C2 module_em input")
    require_hash(Path(row["source_path"]), BASE_SOURCE_SHA256, "base module_em source")
    verify_source_transform(source, proof, Path(row["source_path"]))
    require_hash(Path(row["object_path"]), row["object_sha256"], "base module_em object")
    for module in base["modules"]:
        require_hash(Path(module["path"]), module["sha256"], "C2 module interface")
    for link_input in base["staged_link_inputs"].values():
        require_hash(Path(link_input["path"]), link_input["sha256"], "C2 staged link input")
    return base, row, proof


def stage_modules(base: dict, compile_dir: Path) -> None:
    for row in base["modules"]:
        source = Path(row["path"])
        target = compile_dir / source.name
        if target.exists():
            raise ValueError(f"duplicate staged module: {target.name}")
        shutil.copy2(source, target)
        require_hash(target, row["sha256"], "staged C2 module")


def archive_member_hashes(archive: Path, scratch: Path) -> list[dict[str, str]]:
    names = subprocess.check_output(["ar", "t", str(archive)], text=True).splitlines()
    totals = {name: names.count(name) for name in set(names)}
    seen: dict[str, int] = {}
    result = []
    for index, name in enumerate(names):
        occurrence = seen.get(name, 0) + 1
        seen[name] = occurrence
        if totals[name] == 1:
            payload = subprocess.check_output(["ar", "p", str(archive), name])
        else:
            out_dir = scratch / "archive_members" / str(index)
            out_dir.mkdir(parents=True)
            subprocess.run(["ar", "xN", str(occurrence), str(archive), name],
                           check=True, cwd=out_dir)
            payload = (out_dir / Path(name).name).read_bytes()
        result.append({"index": index, "name": name,
                       "sha256": hashlib.sha256(payload).hexdigest()})
    return result


def build(source: Path, proof_path: Path, scratch: Path, receipt_path: Path) -> dict:
    source, proof_path, scratch = source.resolve(), proof_path.resolve(), scratch.resolve()
    receipt_path = receipt_path.resolve()
    if scratch.exists():
        raise FileExistsError(f"fresh scratch directory already exists: {scratch}")
    if receipt_path.exists():
        raise FileExistsError(f"refusing to replace build receipt: {receipt_path}")
    base, base_row, proof = load_inputs(source, proof_path)
    scratch.mkdir(parents=True)
    compile_dir = scratch / "compile"
    preprocessed_dir = scratch / "preprocessed"
    logs = scratch / "logs"
    link_inputs_dir = scratch / "link_inputs"
    compile_dir.mkdir()
    preprocessed_dir.mkdir()
    logs.mkdir()
    link_inputs_dir.mkdir()
    stage_modules(base, compile_dir)

    compile_row = dict(base_row)
    compiled = overlay.preprocess_and_compile(
        compile_row, source, scratch, compile_dir, quiet_arg_temporaries=False,
    )
    base_archive = Path(base["archive_command"][2])
    staged_archive = scratch / "libwrflib_pr107_t39.a"
    shutil.copy2(base_archive, staged_archive)
    before_members = archive_member_hashes(base_archive, scratch / "archive_before")
    subprocess.run(["ar", "r", str(staged_archive), str(compile_dir / MEMBER)],
                   check=True, cwd=scratch)
    after_members = archive_member_hashes(staged_archive, scratch / "archive_after")
    if [(row["index"], row["name"]) for row in before_members] != \
            [(row["index"], row["name"]) for row in after_members]:
        raise ValueError("C2 archive member set changed")
    changed_indices = [index for index, (before, after) in
                       enumerate(zip(before_members, after_members))
                       if before["sha256"] != after["sha256"]]
    changed_names = {before_members[index]["name"] for index in changed_indices}
    if changed_names != {MEMBER} or len(changed_indices) != 1:
        raise ValueError(f"unexpected C2 archive occurrence changes: {changed_indices}")

    executable = scratch / "wrf_pr107_t39_capture.exe"
    link_object_rows = []
    link_object_rewrites = {}
    for arg in base["link_argv"]:
        path = Path(arg)
        if path.is_absolute() and path.suffix == ".o":
            digest = sha256(path)
            target = link_inputs_dir / path.name
            if target.exists():
                raise ValueError(f"duplicate link object basename: {path.name}")
            shutil.copy2(path, target)
            require_hash(target, digest, "staged original link object")
            link_object_rows.append({"source_path": str(path), "source_sha256": digest,
                                     "staged_path": str(target), "staged_sha256": sha256(target)})
            link_object_rewrites[str(path)] = str(target)
    link_argv = []
    for arg in base["link_argv"]:
        if arg == base_archive.as_posix():
            link_argv.append(str(staged_archive))
        elif arg == base["executable_path"]:
            link_argv.append(str(executable))
        elif arg in link_object_rewrites:
            link_argv.append(link_object_rewrites[arg])
        else:
            link_argv.append(arg)
    link_cwd = scratch / "link" / "main"
    link_cwd.mkdir(parents=True)
    overlay.run_pinned(link_argv, link_cwd, logs / "link.log",
                       profile=Path(base["compiler_profile_path"]))
    if not executable.is_file() or executable.read_bytes()[:4] != b"\x7fELF":
        raise ValueError("link did not produce an ELF executable")

    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt = {
        "schema": "pr87_native_overlay_build_v1",
        "status": "PASS_OVERLAY_BUILD",
        "identity": "PR107 T39 diagnostic-only C2 selected-object overlay; not a clean build",
        "full_clean_build": False,
        "model_run": False,
        "parent_receipt_path": str(BASE_RECEIPT),
        "parent_receipt_sha256": BASE_RECEIPT_SHA256,
        "compiler_profile_path": base["compiler_profile_path"],
        "compiler_profile_sha256": PROFILE_SHA256,
        "compiler_path": base["compiler_path"],
        "compiler_sha256": base["compiler_sha256"],
        "compiler_version": base["compiler_version"],
        "scratch": str(scratch.resolve()),
        "source_transform_proof": {
            "path": str(proof_path), "sha256": sha256(proof_path),
            "source_path": str(source), "source_sha256": sha256(source),
            "diff_path": proof["diff_path"], "diff_sha256": proof["diff_sha256"],
            "math_source_unchanged": True,
            "producer_target": proof["producer_target"],
            "group_target": proof["group_target"],
            "helpers": proof["helpers"],
        },
        "base_c2_executable_sha256": base["executable_sha256"],
        "base_c2_archive_sha256": base["archive_sha256"],
        "base_archive_member_sha256": before_members,
        "archive_member_sha256": after_members,
        "changed_archive_members": sorted(changed_names),
        "changed_archive_member_indices": changed_indices,
        "original_link_objects": link_object_rows,
        "compiled_overrides": [{
            **compiled,
            "base_source_path": base_row["source_path"],
            "base_source_sha256": base_row["source_sha256"],
            "base_object_sha256": base_row["object_sha256"],
        }],
        "inherited_compiled_overrides": [
            {"member": row["member"], "source_path": row["source_path"],
             "source_sha256": row["source_sha256"], "object_sha256": row["object_sha256"]}
            for row in base["compiled_overrides"] if row["member"] != MEMBER
        ],
        "archive_path": str(staged_archive),
        "archive_sha256": sha256(staged_archive),
        "link_argv": link_argv,
        "link_cwd": str(link_cwd.resolve()),
        "executable_path": str(executable),
        "executable_sha256": sha256(executable),
    }
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True,
                        help="reviewed transformed module_em source")
    parser.add_argument("--proof", type=Path, required=True,
                        help=f"source proof ({PROOF_SCHEMA})")
    parser.add_argument("--scratch", type=Path, required=True,
                        help="new scratch directory; must not already exist")
    parser.add_argument("--receipt", type=Path, required=True,
                        help="output build receipt")
    args = parser.parse_args()
    result = build(args.source, args.proof, args.scratch, args.receipt)
    print(json.dumps({"status": result["status"],
                      "executable_path": result["executable_path"],
                      "executable_sha256": result["executable_sha256"],
                      "changed_archive_members": result["changed_archive_members"],
                      "receipt": str(args.receipt.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
