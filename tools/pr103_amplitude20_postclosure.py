#!/usr/bin/env python3
"""Close the approved A20 baseline/capture pair and bind its 57 source snapshots."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import pr102_capture_noninterference as capture
import pr102_response as response
import pr98_native_effect as native


A_INPUT_SHA256 = "9038d0a26896a630b7048091a97a2c0055b26934513392195eb8e609626e74e2"
BASE_C2_SHA256 = "387f46df03e87b8693a57fdefc4ddb62a848e7a946ce417ee8b3d54d2c62cc9a"
DIAGNOSTIC_SHA256 = "aca04cd72a886d41fedcae51e2bbb9cc0b03688e4b9db96ddd12ebc62981b6e0"
BOUNDARY_SHA256 = "885591e6008e219d0b0f8a5a9c6cc3b48eae097d951d1ed731234108706b25d7"
NAMELIST_SHA256 = "bd668a0f54fdc05996782adf472c78834cfc4829a05645fad8c68531a0be52d3"
BASE_BUILD_SHA256 = "9c4802e12ea1d6a8f3c8b5ef1a5ff72116e5fbdbf9f6c78e906935622d45dafb"
DIAGNOSTIC_BUILD_SHA256 = "c5d63426e89d21cc6de4c857de2b66ec799d6a691c92ab09e5607e61052e31ca"
CAPTURE_BUILD_PATH = Path("/var/tmp/pr102_c2_native_capture_build_v3_20261025/pr102_c2_native_capture_build.json")
CAPTURE_BUILD_SHA256 = "df1e10936d2d69bcc9dac871bd5e17e9b9bc70757b8da01db3b93caec2fe80e8"


def pin(path: Path) -> dict:
    path = path.resolve()
    return {"path": str(path), "sha256": capture.sha256(path), "bytes": path.stat().st_size}


def source_root(receipt_path: Path | dict, expected_input: str) -> tuple[Path, dict]:
    record = json.loads(receipt_path.read_text()) if isinstance(receipt_path, Path) else receipt_path
    source_label = str(receipt_path) if isinstance(receipt_path, Path) else "A source capture"
    if (record.get("schema") != "pr102_native_source_capture_v1" or
            record.get("status") != "COMPLETE" or
            record.get("candidate_wrfinput_sha256") != expected_input or
            record.get("completed_steps") != 1 or
            set(record.get("captured_sources", [])) != {"RU", "RV", "MUDF"} or
            record.get("noninterference", {}).get("status") != "PASS"):
        raise ValueError(f"source capture does not bind the expected one-step input: {source_label}")
    files = []
    for row in record.get("artifacts", []):
        path = Path(row["path"])
        if capture.sha256(path) != row.get("sha256"):
            raise ValueError(f"source capture artifact changed: {path}")
        if path.name.startswith("pr98_") and path.suffix == ".bin":
            files.append(path)
    if len(files) != 57 or len({path.parent for path in files}) != 1:
        raise ValueError(f"source capture must bind 57 colocated PR98 snapshots: {source_label}")
    return files[0].parent, record


def first_native_response(hydro_path: Path, projected_path: Path, structured_path: Path,
                          amplitude_receipt_path: Path) -> dict:
    hydro_root, hydro = source_root(hydro_path, "46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c")
    projected_root, projected = source_root(projected_path, "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3")
    structured_root, structured = source_root(structured_path, "b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f")
    amplitude_root, amplitude = source_root(amplitude_receipt_path, A_INPUT_SHA256)
    builds = {item.get("diagnostic_build_receipt_sha256")
              for item in (hydro, projected, structured, amplitude)}
    exes = {item.get("diagnostic_executable_sha256")
            for item in (hydro, projected, structured, amplitude)}
    if builds != {CAPTURE_BUILD_SHA256} or exes != {DIAGNOSTIC_SHA256}:
        raise ValueError("H/P/N/A captures must share the pinned ACA04 executable and build")

    masks, composition_sha = response._fixed_masks(native.COMPOSITION)
    support = masks["support"]
    hpa = native.analyze_native_capture(
        {"OFF": hydro_root, "HYDRO": projected_root, "COUPLED": amplitude_root}, support)
    hna = native.analyze_native_capture(
        {"OFF": hydro_root, "HYDRO": structured_root, "COUPLED": amplitude_root}, support)
    hpa_rates = response._dry_column_rates(
        {"H": hydro_root, "P": projected_root, "N": amplitude_root},
        {"H": {"input_sha256": hydro["candidate_wrfinput_sha256"]},
         "P": {"input_sha256": projected["candidate_wrfinput_sha256"]},
         "N": {"input_sha256": amplitude["candidate_wrfinput_sha256"]}}, support)
    hna_rates = response._dry_column_rates(
        {"H": hydro_root, "P": structured_root, "N": amplitude_root},
        {"H": {"input_sha256": hydro["candidate_wrfinput_sha256"]},
         "P": {"input_sha256": structured["candidate_wrfinput_sha256"]},
         "N": {"input_sha256": amplitude["candidate_wrfinput_sha256"]}}, support)
    report = {
        "schema": "pr103_first_native_source_response_v1", "status": "DESCRIPTIVE_ONLY",
        "fixed_support_composition_sha256": composition_sha,
        "diagnostic_executable_sha256": DIAGNOSTIC_SHA256,
        "diagnostic_build_receipt_sha256": next(iter(builds)),
        "source_capture_receipts": {"H": pin(hydro_path), "P": pin(projected_path),
                                    "N": pin(structured_path),
                                    "A": {"candidate_wrfinput_sha256": amplitude["candidate_wrfinput_sha256"],
                                          "run_receipt": amplitude["run_receipt"]}},
        "native_source_triplets": {
            "A_minus_P_and_H": {"role_mapping": {"H": "reference", "P": "contrast", "A": "candidate"},
                                 "metrics": rename_native_roles(hpa, "P")},
            "A_minus_N_and_H": {"role_mapping": {"H": "reference", "N": "contrast", "A": "candidate"},
                                 "metrics": rename_native_roles(hna, "N")}},
        "dry_column_source_rates": {
            "A_minus_P_and_H": {"role_mapping": {"H": "H", "P": "P", "N": "A"},
                                 "metrics": rename_native_roles(hpa_rates, "P")},
            "A_minus_N_and_H": {"role_mapping": {"H": "H", "P": "N", "N": "A"},
                                 "metrics": rename_native_roles(hna_rates, "N")}},
        "interpretation": "Descriptive first-step source-array and dry-column contrasts on the frozen support; no norm is an admission gate or physical closure.",
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED"}
    return report


def run_receipt(root: Path, *, control: bool) -> dict:
    expected_arm = "AMPLITUDE_BASELINE20" if control else "AMPLITUDE_CAPTURE"
    expected_executable = BASE_C2_SHA256 if control else DIAGNOSTIC_SHA256
    receipt = capture._valid_closed_receipt(
        root, "N", control=control, expected_arm=expected_arm,
        expected_input=A_INPUT_SHA256, expected_steps=1,
        expected_executable=expected_executable)
    capture.require_one_step_timestamp(receipt)
    if (receipt.get("candidate_wrfbdy_sha256") != BOUNDARY_SHA256 or
            receipt.get("candidate_namelist_sha256") != NAMELIST_SHA256):
        raise ValueError(f"{expected_arm} boundary or 20-second namelist differs from the approved plan")
    expected_build = BASE_BUILD_SHA256 if control else DIAGNOSTIC_BUILD_SHA256
    if receipt.get("candidate_build", {}).get("receipt_sha256") != expected_build:
        raise ValueError(f"{expected_arm} build receipt differs from the approved plan")
    return receipt


def closed_run_artifacts(root: Path, receipt: dict) -> list[dict]:
    rows = [pin(root / "receipt.json"), pin(root / "preflight.json"),
            pin(root / "launch_provenance.json")]
    for row in receipt.get("generated_files", []):
        path = root / "run" / row["path"]
        if capture.sha256(path) != row.get("sha256"):
            raise ValueError(f"closed generated output changed: {path}")
        rows.append(pin(path))
    for row in receipt.get("compressed_outputs", []):
        path = root / "run" / row["compressed_path"]
        if capture.sha256(path) != row.get("compressed_sha256"):
            raise ValueError(f"closed compressed output changed: {path}")
        rows.append(pin(path))
    build = receipt.get("candidate_build", {})
    if build.get("receipt_path"):
        rows.append(pin(Path(build["receipt_path"])))
    return rows


def loaded_local_sources() -> list[dict]:
    repo = Path(__file__).resolve().parents[1]
    rows = {}
    for module in tuple(sys.modules.values()):
        source = getattr(module, "__file__", None)
        if not source:
            continue
        path = Path(source).resolve()
        try:
            path.relative_to(repo)
        except ValueError:
            continue
        if path.is_file():
            rows[str(path)] = pin(path)
    rows[str(Path(__file__).resolve())] = pin(Path(__file__).resolve())
    return list(rows.values())


def rename_native_roles(value, contrast: str):
    role_names = {
        "OFF": "H", "HYDRO": contrast, "COUPLED": "A",
        "h_H_minus_O": f"{contrast}_minus_H",
        "b_C_minus_H": f"A_minus_{contrast}",
        "net_C_minus_O": "A_minus_H",
        "H": "H", "P": contrast, "N": "A",
        "P_minus_H": f"{contrast}_minus_H", "N_minus_P": f"A_minus_{contrast}",
        "N_minus_H": "A_minus_H", "HYDRO_minus_OFF": f"{contrast}_minus_H",
        "COUPLED_minus_HYDRO": f"A_minus_{contrast}",
        "COUPLED_minus_OFF": "A_minus_H", "C_minus_H": f"A_minus_{contrast}",
    }
    if isinstance(value, dict):
        return {role_names.get(key, key): rename_native_roles(item, contrast)
                for key, item in value.items()}
    if isinstance(value, list):
        return [rename_native_roles(item, contrast) for item in value]
    return value


def close_pair(baseline_root: Path, capture_root: Path, output_dir: Path,
               hydro_capture: Path, projected_capture: Path, structured_capture: Path) -> dict:
    baseline_root, capture_root = baseline_root.resolve(), capture_root.resolve()
    baseline = run_receipt(baseline_root, control=True)
    diagnostic = run_receipt(capture_root, control=False)
    if (baseline.get("candidate_wrfinput_sha256") != diagnostic.get("candidate_wrfinput_sha256") or
            baseline.get("candidate_wrfbdy_sha256") != diagnostic.get("candidate_wrfbdy_sha256") or
            baseline.get("candidate_namelist_sha256") != diagnostic.get("candidate_namelist_sha256") or
            baseline.get("expected_model_timestamps") != diagnostic.get("expected_model_timestamps")):
        raise ValueError("A20 baseline/capture candidate, boundary, namelist, or timestamp differs")

    baseline_receipt_path, diagnostic_receipt_path = baseline_root / "receipt.json", capture_root / "receipt.json"
    source_outputs = capture.receipt_bound_source_outputs(capture_root, diagnostic)
    if len(source_outputs) != 57 or len({Path(row["path"]).name for row in source_outputs}) != 57:
        raise ValueError("A diagnostic receipt must bind exactly 57 distinct PR98 source snapshots")

    hydro_root, hydro_record = source_root(hydro_capture,
        "46760bdf03e42cbc8e1f5b415e1b304b535d369689f95a421a287d1eb90b679c")
    projected_root, projected_record = source_root(projected_capture,
        "10aff32bf15887a43141efbb1b14945234e8bbce741a89904d328fb3b1d75cb3")
    structured_root, structured_record = source_root(structured_capture,
        "b26e5f3d712732c3459d59b82a4b44fe53eebd9be1fd450d13640d2d8398343f")
    before_rows = [*closed_run_artifacts(baseline_root, baseline),
                   *closed_run_artifacts(capture_root, diagnostic)]
    for path, record in ((hydro_capture, hydro_record), (projected_capture, projected_record),
                         (structured_capture, structured_record)):
        before_rows.extend([pin(path), *record.get("artifacts", [])])
    before_rows.extend(loaded_local_sources())
    source_before = sorted({(row["path"], row["sha256"]):
                            {"path": str(Path(row["path"]).resolve()), "sha256": row["sha256"]}
                            for row in before_rows}.values(), key=lambda row: row["path"])
    for row in source_before:
        path = Path(row["path"])
        if capture.sha256(path) != row["sha256"]:
            raise ValueError(f"source/artifact pin changed before comparison: {path}")

    overlay_path = Path(diagnostic["candidate_build"]["receipt_path"])
    build_path = CAPTURE_BUILD_PATH
    build = json.loads(build_path.read_text())
    overlay = json.loads(overlay_path.read_text())
    if (capture.sha256(build_path) != CAPTURE_BUILD_SHA256 or
            capture.sha256(overlay_path) != DIAGNOSTIC_BUILD_SHA256 or
            build.get("diagnostic_build_receipt_sha256") != capture.sha256(overlay_path) or
            build.get("schema") != "pr102_c2_native_capture_build_v1" or
            build.get("status") != "PASS_C2_CAPTURE_OVERLAY" or
            build.get("base_c2_executable_sha256") != BASE_C2_SHA256 or
            build.get("executable_sha256") != DIAGNOSTIC_SHA256 or
            overlay.get("executable_sha256") != DIAGNOSTIC_SHA256):
        raise ValueError("A source capture does not bind the pinned ACA04 C2 diagnostic build")

    t0 = capture.compare_t0(capture_root, diagnostic, baseline_root, baseline)
    first20 = capture.compare_first20(diagnostic, baseline)
    t1 = capture.compare_t1_post(capture_root, diagnostic, baseline_root, baseline)
    if (len(t0["fields"]) != 30 or len(t1["fields"]) != 18 or
            not all(row["equal"] for row in t0["fields"].values()) or
            not all(row["equal"] for row in t1["fields"].values())):
        raise ValueError("A20 T0/T1 exact noninterference comparison failed")
    artifacts = [pin(baseline_receipt_path), pin(diagnostic_receipt_path),
                 t0["diagnostic_file"], t0["control_file"],
                 t1["diagnostic_compressed"], t1["control_compressed"],
                 pin(baseline_root / "preflight.json"), pin(capture_root / "preflight.json"),
                 pin(baseline_root / "launch_provenance.json"),
                 pin(capture_root / "launch_provenance.json"), pin(build_path), pin(overlay_path),
                 *source_outputs]
    for root, receipt in ((baseline_root, baseline), (capture_root, diagnostic)):
        trace = capture.verify_output(root, receipt, "pr85_joint_moment_stages.raw", compressed=True)
        artifacts.append(pin(trace))
    artifacts = list({(row["path"], row["sha256"]): row for row in artifacts}.values())
    capture_receipt = {
        "schema": "pr102_native_source_capture_v1", "status": "COMPLETE",
        "role": "AMPLITUDE", "candidate_wrfinput_sha256": A_INPUT_SHA256,
        "baseline_c2_executable_sha256": BASE_C2_SHA256,
        "diagnostic_executable_sha256": DIAGNOSTIC_SHA256,
        "diagnostic_build_receipt": pin(build_path),
        "diagnostic_build_receipt_sha256": capture.sha256(build_path),
        "captured_sources": ["RU", "RV", "MUDF"], "completed_steps": 1,
        "run_receipt": pin(diagnostic_receipt_path),
        "control_receipt": pin(baseline_receipt_path),
        "namelist_sha256": diagnostic["candidate_namelist_sha256"],
        "boundary_sha256": diagnostic["candidate_wrfbdy_sha256"],
        "launch_environment": diagnostic["launch_environment"],
        "noninterference": {"status": "PASS"},
        "artifacts": artifacts,
        "source_snapshot_count": len(source_outputs),
        "physical_approval": "FAIL_OPEN",
        "observation_skill": "NOT_EVALUATED",
    }
    native_response = first_native_response(hydro_capture, projected_capture, structured_capture,
                                           capture_receipt)
    source_after = [{"path": row["path"], "sha256": capture.sha256(Path(row["path"]))}
                    for row in source_before]
    if source_before != source_after:
        raise ValueError("A20 postclosure source/artifact pins changed during readback")
    noninterference = {
        "schema": "pr103_amplitude20_noninterference_v1",
        "status": "PASS_CAPTURE_NONINTERFERENCE",
        "candidate_input_sha256": A_INPUT_SHA256,
        "control_arm": "AMPLITUDE_BASELINE20",
        "diagnostic_arm": "AMPLITUDE_CAPTURE",
        "control_receipt": pin(baseline_receipt_path),
        "diagnostic_receipt": pin(diagnostic_receipt_path),
        "control_executable_sha256": BASE_C2_SHA256,
        "diagnostic_executable_sha256": DIAGNOSTIC_SHA256,
        "t0_history": t0, "first20_trace": first20, "t1_post": t1,
        "source_capture_outputs": source_outputs, "evidence_artifacts": artifacts,
        "source_bindings_before": source_before, "source_bindings_after": source_after,
        "scope": "Exact field/record capture noninterference for the approved A input at 20 seconds; no physical acceptance.",
        "physical_approval": "FAIL_OPEN", "observation_skill": "NOT_EVALUATED",
        "created_utc": datetime.now(timezone.utc).isoformat(),
    }
    capture_receipt["noninterference"]["evidence"] = noninterference
    if output_dir.exists():
        raise FileExistsError(f"refusing to replace A20 closure output directory: {output_dir}")
    output_dir.mkdir(parents=True)
    noninterference_path = output_dir / "a20_noninterference.json"
    source_receipt_path = output_dir / "amplitude_source_capture.json"
    noninterference_path.write_text(json.dumps(noninterference, indent=2, sort_keys=True) + "\n")
    source_receipt_path.write_text(json.dumps(capture_receipt, indent=2, sort_keys=True) + "\n")
    native_response["source_capture_receipts"]["A"] = pin(source_receipt_path)
    native_response_path = output_dir / "first_native_response.json"
    native_response_path.write_text(json.dumps(native_response, indent=2, sort_keys=True) + "\n")
    return {"noninterference": pin(noninterference_path), "source_capture": pin(source_receipt_path),
            "first_native_response": pin(native_response_path),
            "status": "PASS_CAPTURE_NONINTERFERENCE", "source_snapshot_count": len(source_outputs)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-root", type=Path, required=True)
    parser.add_argument("--capture-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--capture-hydro", type=Path, required=True)
    parser.add_argument("--capture-p", type=Path, required=True)
    parser.add_argument("--capture-n", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(close_pair(args.baseline_root, args.capture_root, args.output_dir,
                                args.capture_hydro, args.capture_p, args.capture_n), indent=2))


if __name__ == "__main__":
    main()
