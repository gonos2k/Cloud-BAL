#!/usr/bin/env bash
# Run the maintained cold LAPSPREP caller against the actual upstream reader.
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd -P)
repo_root=$(cd "$script_dir/.." && pwd -P)
workspace_root=$(cd "$repo_root/.." && pwd -P)
upstream="$workspace_root/klaps-v5.0_"
verifier="$repo_root/tests/verify_qbal_lapsprep.py"

if [[ $# != 2 ]]; then
  printf 'usage: run_qbal_lapsprep_tests.sh WRITER_SCRATCH_ROOT RUN_ROOT\n' >&2
  exit 2
fi
writer_input=$(cd "$1" && pwd -P)
run_root=$2
if [[ "$run_root" != /* ]]; then
  run_root="$(pwd -P)/$run_root"
fi
[[ -f "$verifier" ]] || { printf 'missing reader verifier: %s\n' "$verifier" >&2; exit 2; }
[[ -d "$upstream/src/lapsprep" ]] || {
  printf 'pinned upstream LAPSPREP source is unavailable: %s\n' "$upstream" >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"

nf_config="$upstream/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
netcdff_archive="$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a"
netcdf_archive="$upstream/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/lib/libnetcdf.a"
nf_fortran_include="$(dirname "$(dirname "$nf_config")")/include"
netcdf_c_include="$(dirname "$(dirname "$netcdf_archive")")/include"
[[ -x "$nf_config" && -f "$netcdff_archive" && -f "$netcdf_archive" ]] || {
  printf 'pinned NetCDF Fortran/C archives are unavailable\n' >&2
  exit 2
}
verify_hash() {
  local path=$1 expected=$2 actual
  actual=$(sha256sum "$path" | cut -d' ' -f1)
  [[ "$actual" == "$expected" ]] || {
    printf 'pinned dependency hash mismatch: %s\n' "$path" >&2
    exit 2
  }
}
verify_hash "$nf_config" e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5
verify_hash "$netcdff_archive" f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39
verify_hash "$netcdf_archive" f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288
read -r -a nf_fflags <<<"$($nf_config --fflags)"
read -r -a nf_flibs <<<"$($nf_config --flibs)"

[[ -f "$writer_input/manifest.json" && -d "$writer_input/O0" && -d "$writer_input/O2" ]] || {
  printf 'writer input must contain manifest.json and O0/O2 variants: %s\n' "$writer_input" >&2
  exit 2
}
levels='O0 O2'
writer_root="$writer_input"
writer_manifest="$writer_root/manifest.json"
[[ -f "$writer_manifest" ]] || {
  printf 'writer manifest is required: %s\n' "$writer_manifest" >&2
  exit 2
}
python3 - "$writer_manifest" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path = Path(sys.argv[1])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
if manifest.get("status") != "PASS_SCOPED":
    raise SystemExit("writer manifest is not PASS_SCOPED")
artifacts = manifest.get("artifacts_sha256")
if not isinstance(artifacts, dict):
    raise SystemExit("writer manifest has no artifact hashes")
for relative, expected in artifacts.items():
    path = manifest_path.parent / relative
    if not path.is_file():
        raise SystemExit(f"writer artifact is missing: {path}")
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise SystemExit(f"writer artifact hash mismatch: {path}")
for level in ("O0", "O2"):
    required = [manifest_path.parent / level / "candidate.bin"]
    required.extend((manifest_path.parent / level / "out" / "balance").rglob("*"))
    for path in required:
        if path.is_dir():
            continue
        if not path.is_file():
            raise SystemExit(f"writer artifact is missing: {path}")
        if path.relative_to(manifest_path.parent).as_posix() not in artifacts:
            raise SystemExit(f"writer artifact is not in manifest: {path}")
PY

[[ ! -e "$run_root" ]] || {
  printf 'RUN_ROOT must be a new path: %s\n' "$run_root" >&2
  exit 2
}
mkdir -p "$(dirname "$run_root")"

compile_level() {
  local level=$1 level_root=$2
  local build="$level_root/build"
  local flags=()
  if [[ "$level" == O0 ]]; then
    flags=("${CLOUD_BAL_FREE_FLAGS[@]}")
  else
    flags=("${CLOUD_BAL_REPRO_FLAGS[@]}")
  fi
  mkdir -p "$build"
  pushd "$build" >/dev/null
  pwd -P > "$level_root/build.cwd"
  : > "$level_root/compiler_argv.jsonl"
  record_argv() {
    local source=$1
    shift
    python3 - "$source" "$@" >> "$level_root/compiler_argv.jsonl" <<'PY'
import json
import sys

source, *argv = sys.argv[1:]
print(json.dumps({"source": source, "argv": argv}, sort_keys=True))
PY
    "$@"
  }
  compile_one() {
    local source=$1 object=$2
    record_argv "$source" "$CLOUD_BAL_FC" -c "${flags[@]}" \
      -module "$build" -I "$build" -I "$upstream/src/include" \
      "${nf_fflags[@]}" "$source" -o "$build/$object"
  }
  compile_one "$upstream/src/lapsprep/module_constants.f90" constants.o
  compile_one "$upstream/src/lapsprep/module_date_pack.f90" date_pack.o
  compile_one "$upstream/src/lapsprep/module_laps_static.f90" laps_static.o
  compile_one "$repo_root/tests/qbal_lapsprep_stubs.f90" stubs.o
  compile_one "$repo_root/src/common/cloud_bal_field_contracts.f90" contracts.o
  compile_one "$repo_root/src/common/cloud_bal_moisture.f90" moisture.o
  compile_one "$repo_root/src/common/cloud_bal_state.f90" cloud_bal_state.o
  compile_one "$repo_root/src/common/cloud_bal_grid_geometry.f90" cloud_bal_grid_geometry.o
  compile_one "$repo_root/src/common/cloud_bal_column_physics.f90" cloud_bal_column_physics.o
  compile_one "$repo_root/src/common/cloud_bal_balance_operator.f90" cloud_bal_balance_operator.o
  compile_one "$repo_root/src/common/cloud_bal_pipeline.f90" cloud_bal_pipeline.o
  compile_one "$repo_root/src/common/cloud_bal_real_netcdf.f90" cloud_bal_real_netcdf.o
  compile_one "$repo_root/src/common/cloud_bal_stage_payload.f90" stage_payload.o
  compile_one "$repo_root/src/common/cloud_bal_stage_context.f90" stage_context.o
  compile_one "$repo_root/src/common/cloud_bal_lapsprep_adapter.f90" lapsprep_adapter.o
  compile_one "$repo_root/src/common/cloud_bal_pressure_analysis.f90" pressure_analysis.o
  compile_one "$repo_root/src/common/cloud_bal_wps_adapter.f90" wps_adapter.o
  compile_one "$repo_root/src/lapsprep/module_setup.f90" setup.o
  compile_one "$repo_root/src/lapsprep/module_lapsprep_wps.f90" wps.o
  compile_one "$repo_root/src/lapsprep/lapsprep.f90" lapsprep.o
  record_argv "link:lapsprep.exe" "$CLOUD_BAL_FC" "${flags[@]}" \
    "$build/lapsprep.o" "$build/wps.o" "$build/setup.o" "$build/constants.o" \
    "$build/date_pack.o" "$build/laps_static.o" "$build/stubs.o" \
    "$build/contracts.o" "$build/moisture.o" "$build/cloud_bal_state.o" \
    "$build/cloud_bal_grid_geometry.o" "$build/cloud_bal_column_physics.o" \
    "$build/cloud_bal_balance_operator.o" "$build/cloud_bal_pipeline.o" \
    "$build/cloud_bal_real_netcdf.o" "$build/stage_payload.o" \
    "$build/stage_context.o" "$build/lapsprep_adapter.o" \
    "$build/pressure_analysis.o" "$build/wps_adapter.o" \
    "${nf_flibs[@]}" -o "$build/lapsprep.exe"
  python3 - "$repo_root/src/lapsprep/lapsprep.f90" "$level_root/k300_negative.f90" <<'PY'
from pathlib import Path
import sys

source = Path(sys.argv[1]).read_text(encoding="utf-8")
target = "if (jaxsbn .and. k300 .eq. 0) THEN"
replacement = "if (k300 .eq. 0) THEN"
if source.count(target) != 1:
    raise SystemExit("k300 negative-control target is not unique")
Path(sys.argv[2]).write_text(source.replace(target, replacement), encoding="utf-8")
PY
  record_argv "$level_root/k300_negative.f90" "$CLOUD_BAL_FC" -c "${flags[@]}" \
    -module "$build" -I "$build" -I "$upstream/src/include" \
    "${nf_fflags[@]}" "$level_root/k300_negative.f90" -o "$build/lapsprep_k300_negative.o"
  record_argv "link:lapsprep_k300_negative.exe" "$CLOUD_BAL_FC" "${flags[@]}" \
    "$build/lapsprep_k300_negative.o" "$build/wps.o" "$build/setup.o" \
    "$build/constants.o" "$build/date_pack.o" "$build/laps_static.o" "$build/stubs.o" \
    "$build/contracts.o" "$build/moisture.o" "$build/cloud_bal_state.o" \
    "$build/cloud_bal_grid_geometry.o" "$build/cloud_bal_column_physics.o" \
    "$build/cloud_bal_balance_operator.o" "$build/cloud_bal_pipeline.o" \
    "$build/cloud_bal_real_netcdf.o" "$build/stage_payload.o" \
    "$build/stage_context.o" "$build/lapsprep_adapter.o" \
    "$build/pressure_analysis.o" "$build/wps_adapter.o" \
    "${nf_flibs[@]}" -o "$build/lapsprep_k300_negative.exe"
  popd >/dev/null
}

hash_inputs() {
  local level=$1 variant=$2 level_root=$3
  python3 - "$level_root/input_hashes.sha256" "$variant" "$repo_root" "$upstream" \
    "$writer_manifest" "$nf_config" "$netcdff_archive" "$netcdf_archive" \
    "$nf_fortran_include" "$netcdf_c_include" "$CLOUD_BAL_FC" "$cloud_bal_imf" \
    "$cloud_bal_intlc" "$cloud_bal_setvars" <<'PY'
import hashlib
import sys
from pathlib import Path

output, variant, repo, upstream, writer_manifest, nf_config, netcdff, netcdf, nf_include, nc_include, compiler, imf, intlc, setvars = map(Path, sys.argv[1:])
paths = [
    variant / "candidate.bin", writer_manifest, nf_config, netcdff, netcdf,
    compiler, imf, intlc, setvars,
    repo / "tests/intel_toolchain.sh", repo / "tests/qbal_lapsprep_stubs.f90",
    repo / "tests/run_qbal_lapsprep_tests.sh", repo / "tests/verify_qbal_lapsprep.py",
    repo / "tests/verify_qbal_writer.py", repo / "tools/compare_baseline.py",
    repo / "src/lapsprep/lapsprep.f90", repo / "src/lapsprep/module_setup.f90",
    repo / "src/lapsprep/module_lapsprep_wps.f90",
    repo / "src/common/cloud_bal_field_contracts.f90",
    repo / "src/common/cloud_bal_moisture.f90",
    repo / "src/common/cloud_bal_state.f90",
    repo / "src/common/cloud_bal_grid_geometry.f90",
    repo / "src/common/cloud_bal_column_physics.f90",
    repo / "src/common/cloud_bal_balance_operator.f90",
    repo / "src/common/cloud_bal_pipeline.f90",
    repo / "src/common/cloud_bal_real_netcdf.f90",
    repo / "src/common/cloud_bal_stage_payload.f90",
    repo / "src/common/cloud_bal_stage_context.f90",
    repo / "src/common/cloud_bal_lapsprep_adapter.f90",
    repo / "src/common/cloud_bal_pressure_analysis.f90",
    repo / "src/common/cloud_bal_wps_adapter.f90",
    upstream / "src/lapsprep/module_constants.f90",
    upstream / "src/lapsprep/module_date_pack.f90",
    upstream / "src/lapsprep/module_laps_static.f90",
]
paths.extend(sorted((upstream / "src/include").glob("*")))
paths.extend(sorted(nf_include.glob("*")))
paths.extend(sorted(nc_include.glob("*")))
paths.extend(sorted((variant / "out" / "balance").rglob("*")))
paths = [path for path in paths if path.is_file()]
def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()
output.write_text("".join(f"{digest(path)}  {path}\n" for path in paths), encoding="ascii")
PY
}

run_level() {
  local level=$1 variant=$2 level_root=$3
  local stamp wps_path status
  stamp=$(python3 "$verifier" stage "$variant" "$level_root")
  [[ "$stamp" == 231380333 ]] || {
    printf 'unexpected staged stamp for %s: %s\n' "$level" "$stamp" >&2
    exit 1
  }
  printf '%s\n' "$stamp" > "$level_root/stage.stamp"
  hash_inputs "$level" "$variant" "$level_root"
  compile_level "$level" "$level_root" > "$level_root/build.log" 2>&1 || {
    cat "$level_root/build.log" >&2
    exit 1
  }
  if ! sha256sum -c --strict "$level_root/input_hashes.sha256" > "$level_root/input_verification.log"; then
    cat "$level_root/input_verification.log" >&2
    exit 1
  fi

  # The old unconditional k300 check must reject this candidate. The Intel
  # runtime may return zero for an unlabelled STOP, so use the named message
  # and output absence as the control result.
  set +e
  (
    cd "$level_root"
    pwd -P > run.cwd
    env -u CLOUD_BAL_STAGE_MODE -u CLOUD_BAL_STAGE_CONTEXT \
      -u CLOUD_BAL_SHADOW_EXPERIMENT LAPS_DATA_ROOT="$level_root" \
      CLOUD_BAL_WPS_OUTPUT="$level_root/k300-negative.wps" \
      "$level_root/build/lapsprep_k300_negative.exe" "$stamp"
  ) > "$level_root/k300_negative.log" 2>&1
  status=$?
  set -e
  grep -q 'Could not find k300!' "$level_root/k300_negative.log" || {
    cat "$level_root/k300_negative.log" >&2
    printf 'k300 negative control lost its named rejection: %s\n' "$level" >&2
    exit 1
  }
  [[ ! -e "$level_root/k300-negative.wps" && ! -e "$level_root/reader_state.bin" ]] || {
    printf 'k300 negative control produced output: %s\n' "$level" >&2
    exit 1
  }
  python3 - "$level_root/k300_negative.json" "$status" <<'PY'
import json
import sys
from pathlib import Path

Path(sys.argv[1]).write_text(json.dumps({
    "status": "REJECTED",
    "reason": "Could not find k300!",
    "exit_status": int(sys.argv[2]),
    "output_created": False,
    "scope": "legacy unconditional 300 hPa guard control",
}, indent=2) + "\n", encoding="utf-8")
PY

  set +e
  (
    cd "$level_root"
    pwd -P > run.cwd
    env -u CLOUD_BAL_STAGE_MODE -u CLOUD_BAL_STAGE_CONTEXT \
      -u CLOUD_BAL_SHADOW_EXPERIMENT LAPS_DATA_ROOT="$level_root" \
      CLOUD_BAL_WPS_OUTPUT="$level_root/wps.out" \
      "$level_root/build/lapsprep.exe" "$stamp"
  ) > "$level_root/lapsprep.log" 2>&1
  status=$?
  set -e
  if (( status != 0 )); then
    cat "$level_root/lapsprep.log" >&2
    printf 'actual LAPSPREP caller failed for %s\n' "$level" >&2
    exit 1
  fi
  [[ -s "$level_root/wps.out" && -s "$level_root/reader_state.bin" ]] || {
    cat "$level_root/lapsprep.log" >&2
    printf 'reader handoff outputs are missing for %s\n' "$level" >&2
    exit 1
  }
  python3 "$verifier" verify "$variant" "$level_root" "$level_root/wps.out" > "$level_root/verify.json"
  python3 "$verifier" controls "$variant" "$level_root" "$level_root/wps.out" > "$level_root/controls.json"
  if ! sha256sum -c --strict "$level_root/input_hashes.sha256" > "$level_root/input_verification_final.log"; then
    cat "$level_root/input_verification_final.log" >&2
    exit 1
  fi
  printf 'Actual cold LAPSPREP reader handoff %s PASS_SCOPED\n' "$level"
}

for level in $levels; do
  variant="$writer_root/$level"
  [[ -d "$variant" ]] || { printf 'missing writer variant: %s\n' "$variant" >&2; exit 2; }
  level_root="$run_root/$level"
  run_level "$level" "$variant" "$level_root"
done

python3 - "$run_root/manifest.json" "$writer_manifest" "$run_root" "$levels" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

manifest_path, writer_manifest, run_root, level_text = sys.argv[1:]
root = Path(run_root)
levels = level_text.split()
results = []
for level in levels:
    level_root = root / level
    results.append({
        "level": level,
        "verify": json.loads((level_root / "verify.json").read_text()),
        "controls": json.loads((level_root / "controls.json").read_text()),
        "k300_negative_control": json.loads((level_root / "k300_negative.json").read_text()),
        "compiler_argv": [json.loads(line) for line in
                          (level_root / "compiler_argv.jsonl").read_text().splitlines()],
        "build_cwd": (level_root / "build.cwd").read_text().strip(),
        "run_cwd": (level_root / "run.cwd").read_text().strip(),
        "input_hashes_sha256": (level_root / "input_hashes.sha256").read_text().splitlines(),
    })
def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()
artifacts = {}
for path in root.rglob("*"):
    if path.is_file() and path != Path(manifest_path):
        artifacts[str(path.relative_to(root))] = digest(path)
manifest = {
    "status": "PASS_SCOPED",
    "scope": "actual maintained cold LAPSPREP reader and WPS handoff",
    "writer_manifest": writer_manifest,
    "results": results,
    "artifacts_sha256": artifacts,
    "limitations": [
        "synthetic all-valid 6x6x4 BALCON candidate and staged LSX/static/RH",
        "CDF hook is test-only caller observation; no native model startup",
        "legacy WPS filename has minute precision and loses the candidate's 20-second timestamp",
        "hotstart omega-to-W conversion, masks/terrain, native seed/halo and forecast effects remain open",
    ],
}
Path(manifest_path).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
PY
printf 'Actual cold LAPSPREP reader handoff PASS_SCOPED manifest: %s\n' "$run_root/manifest.json"
