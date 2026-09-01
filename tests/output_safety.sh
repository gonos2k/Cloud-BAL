#!/usr/bin/env bash
# Resolve one generated-output path below its dedicated scratch subtree.

cloud_bal_output_under() {
  local resolved allowed_root allowed_lexical scratch_root
  scratch_root=$(realpath -m "$repo_root/scratch")
  allowed_lexical=$(realpath -ms "$2")
  case $allowed_lexical in
    "$scratch_root"/*) ;;
    *)
      printf 'invalid generated-output root: %s\n' "$allowed_lexical" >&2
      return 2
      ;;
  esac
  allowed_root=$(realpath -m "$allowed_lexical")
  if [[ $allowed_root != "$allowed_lexical" ]]; then
    printf 'generated-output root cannot contain a symlink: %s\n' \
      "$allowed_lexical" >&2
    return 2
  fi
  resolved=$(realpath -m "$1")
  case $resolved in
    "$allowed_root"/*)
      case $resolved in
        */generations/*|*/current/*)
          printf 'generated output cannot modify an immutable generation: %s\n' \
            "$resolved" >&2
          return 2
          ;;
        *) printf '%s\n' "$resolved" ;;
      esac
      ;;
    *)
      printf 'generated output must stay below %s: %s\n' \
        "$allowed_root" "$resolved" >&2
      return 2
      ;;
  esac
}

cloud_bal_require_clean_source() {
  if [[ -n $(git -C "$repo_root" status --porcelain --untracked-files=normal) ]]; then
    printf 'evidence tooling requires a clean exact-head source tree\n' >&2
    return 2
  fi
}

cloud_bal_current_evidence() {
  local publication_root=$1 manifest=$2 generation head
  generation=$(python3 "$repo_root/tools/cloud_bal_transaction.py" current \
    "$publication_root")
  head=$(git -C "$repo_root" rev-parse HEAD)
  python3 - "$generation" "$head" "$manifest" <<'PY'
import csv
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path

generation, head, manifest_path = map(Path, sys.argv[1:])
head = str(head)
manifest_path = manifest_path.resolve()

def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

transaction = json.loads((generation / "MANIFEST.json").read_text(encoding="utf-8"))
summary = json.loads((generation / "RUN_SUMMARY.json").read_text(encoding="utf-8"))
with manifest_path.open(newline="", encoding="utf-8") as stream:
    expected_cases = list(csv.DictReader(stream, delimiter="\t"))
if transaction.get("source_commit") != head or summary.get("source_commit") != head:
    raise SystemExit("generation does not belong to the clean source HEAD")
if transaction.get("configuration") != "radar-only-shadow-ifx-2026-v3":
    raise SystemExit("transaction configuration mismatch")
if summary.get("contract") != "radar_only_shadow_ifx_2026_v3":
    raise SystemExit("generation contract mismatch")
if summary.get("numerical_contract") != "PASS":
    raise SystemExit("generation numerical contract mismatch")
if summary.get("input_manifest_sha256") != sha256(manifest_path):
    raise SystemExit("generation input manifest mismatch")
if summary.get("input_cases") != expected_cases:
    raise SystemExit("generation case set mismatch")
case_count = len(expected_cases)
if summary.get("case_count") != case_count or not summary.get("source_tree_clean"):
    raise SystemExit("generation no-skip/clean-source contract mismatch")
if summary.get("hydrometeor_valid_count", -1) + summary.get("rejected_count", -1) != case_count:
    raise SystemExit("generation decision counts mismatch")
if summary.get("science_assessed") is not False or summary.get("promotion_eligible") is not False:
    raise SystemExit("generation authority flags mismatch")
expected_products = {"RUN_SUMMARY.json"}
for case in expected_cases:
    case_id = case["case_id"]
    expected_products.update({f"{case_id}.nc", f"{case_id}.json", f"{case_id}.log"})
actual_products = {item.get("path") for item in transaction.get("products", [])}
if actual_products != expected_products:
    raise SystemExit("generation product inventory mismatch")
expected_valid_time = int(
    datetime.fromisoformat(expected_cases[-1]["valid_time_utc"].replace("Z", "+00:00")).timestamp()
)
if transaction.get("valid_time") != expected_valid_time:
    raise SystemExit("generation valid-time mismatch")
if summary.get("compiler_version") != "ifx (IFX) 2026.0.0 20260331" or \
        summary.get("compiler_sha256") != \
        "909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef":
    raise SystemExit("generation Intel compiler mismatch")
if summary.get("netcdf_fortran_config_sha256") != \
        "e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5" or \
        summary.get("static_grid_sha256") != \
        "384b419c8165457432e8c7ce58e8ab07f57ac07f5a08c2da608880b3240b4b9b":
    raise SystemExit("generation dependency identity mismatch")
build_files = summary.get("build_files")
if not isinstance(build_files, list):
    raise SystemExit("generation build receipt missing")
build_by_label = {}
for item in build_files:
    if not isinstance(item, dict) or item.get("label") in build_by_label:
        raise SystemExit("generation build receipt malformed")
    build_by_label[item.get("label")] = item
    path = Path(str(item.get("path", "")))
    if not path.is_file() or path.is_symlink() or sha256(path) != item.get("sha256"):
        raise SystemExit(f"generation build input changed: {path}")
required_build_labels = {
    "compiler", "setvars", "nf_config", "static_grid", "driver",
    "link_netcdff", "link_netcdf",
}
if not required_build_labels <= set(build_by_label) or \
        not any(label.startswith("runtime_") for label in build_by_label):
    raise SystemExit("generation build receipt is incomplete")
if build_by_label["driver"]["sha256"] != summary.get("driver_sha256"):
    raise SystemExit("generation driver receipt mismatch")
if summary.get("trajectory_horizontal_frame") != "INPUT_WIND_NATIVE_UNRESOLVED" or \
        summary.get("storm_motion_provenance") != \
        "NOT_AVAILABLE_ZERO_TRANSLATION_ASSUMPTION" or \
        summary.get("trajectory_science_assessed") is not False:
    raise SystemExit("generation trajectory provenance mismatch")
valid_reports = 0
rejected_reports = 0
for case in expected_cases:
    case_id = case["case_id"]
    diagnostic = generation / f"{case_id}.nc"
    report = json.loads((generation / f"{case_id}.json").read_text(encoding="utf-8"))
    if report.get("validation_scope") != "NUMERICAL_CONTENT_ONLY" or \
            report.get("numerical_decision") != "VALID" or \
            report.get("artifact_decision") != "UNBOUND":
        raise SystemExit(f"case numerical report mismatch: {case_id}")
    if report.get("sha256") != sha256(diagnostic):
        raise SystemExit(f"case diagnostic/report hash mismatch: {case_id}")
    if report.get("dynamic_balance_decision") != "NOT_AUTHORIZED" or \
            report.get("dynamic_target_cells") != 0 or \
            report.get("balance_changed_cells") != 0:
        raise SystemExit(f"case dynamic authority mismatch: {case_id}")
    if report.get("trajectory_science_decision") != "BLOCKED_MISSING_STORM_MOTION":
        raise SystemExit(f"case trajectory provenance mismatch: {case_id}")
    if report.get("hydrometeor_engineering_decision") == "VALID":
        valid_reports += 1
    elif report.get("hydrometeor_engineering_decision") == "REJECTED":
        rejected_reports += 1
    else:
        raise SystemExit(f"case engineering decision mismatch: {case_id}")
if valid_reports != summary.get("hydrometeor_valid_count") or \
        rejected_reports != summary.get("rejected_count"):
    raise SystemExit("generation per-case decision summary mismatch")
PY
  printf '%s\n' "$generation"
}
