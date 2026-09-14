#!/usr/bin/env bash
# Build and run the isolated raw Cf/Radial decoder against one FQC cycle.
set -euo pipefail

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
repo_root=$(cd "$script_dir/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
raw_root=${1:-$workspace_root/ANAL/NE57/DAIN/2026081613}
raw_timestamp=${RAW_TIMESTAMP:-202608162200}

if [[ -n ${JULDATE:-} || -n ${EPODATE:-} ]]; then
  printf 'JULDATE/EPODATE overrides are unsupported; derive time from raw CF metadata\n' >&2
  exit 2
fi
[[ $raw_timestamp =~ ^[0-9]{12}$ ]] || {
  printf 'RAW_TIMESTAMP must be YYYYMMDDHHMM: %s\n' "$raw_timestamp" >&2
  exit 2
}
[[ -d $raw_root ]] || {
  printf 'raw input directory does not exist: %s\n' "$raw_root" >&2
  exit 2
}

. "$repo_root/tests/intel_toolchain.sh"
setvars_file=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh
nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
[[ -x $nf_config ]] || {
  printf 'pinned NetCDF Fortran config is missing: %s\n' "$nf_config" >&2
  exit 2
}
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"

source_file="$repo_root/src/upstream/radar/klps_radr_dcod.f90"
validator="$repo_root/tests/test_radar_decoder.py"
run_root=$(mktemp -d /tmp/cloud_bal_radar_decoder_run.XXXXXX)
build_root=$(mktemp -d "$repo_root/scratch/radar_decoder_build.XXXXXX")
stage_root=$(mktemp -d "$run_root/stage.XXXXXX")
snapshot_root="$run_root/raw"
input_manifest="$run_root/input_manifest.json"
probe_root="$run_root/probes"
probe_manifest="$run_root/probe_manifest.json"
published_root="$run_root/output"
mkdir "$build_root/mod"
printf 'run_root=%s\n' "$run_root"
printf 'build_root=%s\n' "$build_root"

write_failure() {
  local reason=$1
  local status=${2:-1}
  python3 - "$run_root/failure.json" "$stage_root" "$input_manifest" "$probe_manifest" "$reason" "$status" <<'PY'
import json
import sys
from pathlib import Path

failure, stage, inputs, probes, reason, status = sys.argv[1:]
Path(failure).write_text(json.dumps({
    "schema": 1,
    "status": "FAILED",
    "reason": reason,
    "exit_status": int(status),
    "stage_root": stage,
    "input_manifest": inputs,
    "probe_manifest": probes,
    "scope": "RAW_INPUT_ONLY; failed private staging is retained",
}, indent=2, sort_keys=True) + "\n")
PY
}

# The compiler must see a fresh working directory. Keep compiler flags in a
# JSON record; build_inputs.sha256 remains directly consumable by sha256sum.
cd "$build_root"
python3 - "$build_root/build_flags.json" "$CLOUD_BAL_FC" "$nf_config" \
  "${CLOUD_BAL_FREE_FLAGS[@]}" -- "${nf_flags[@]}" -- "${nf_libs[@]}" <<'PY'
import json
import sys
from pathlib import Path

parts = sys.argv[1:]
output, compiler, nf_config = parts[:3]
rest = parts[3:]
first = rest.index("--")
free_flags = rest[:first]
rest = rest[first + 1:]
second = rest.index("--")
nf_flags = rest[:second]
nf_libs = rest[second + 1:]
Path(output).write_text(json.dumps({
    "compiler": compiler,
    "netcdf_fortran_config": nf_config,
    "working_directory": str(Path.cwd()),
    "free_flags": free_flags,
    "nf_flags": nf_flags,
    "nf_libs": nf_libs,
}, indent=2, sort_keys=True) + "\n")
PY
"$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" -free "${nf_flags[@]}" \
  -module "$build_root/mod" -c "$source_file" -o "$build_root/decoder.o"
"$CLOUD_BAL_FC" "$build_root/decoder.o" "${nf_libs[@]}" \
  -Wl,-Map,"$build_root/link.map" -o "$build_root/decoder"
if ! ldd -r "$build_root/decoder" >"$build_root/runtime.log" 2>&1; then
  printf 'decoder runtime closure inspection failed; log=%s\n' "$build_root/runtime.log" >&2
  exit 1
fi
if rg -n 'not found|undefined symbol' "$build_root/runtime.log"; then
  printf 'decoder runtime closure is incomplete\n' >&2
  exit 1
fi
sha256sum "$build_root/decoder" >"$build_root/executable.sha256"
python3 - "$build_root/decoder" "$build_root/build_flags.json" \
  "$build_root/build_inputs.sha256" "$source_file" "$setvars_file" \
  "$CLOUD_BAL_FC" "$nf_config" \
  "$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/include/netcdf.inc" \
  "$repo_root/tests/intel_toolchain.sh" <<'PY'
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

decoder, flags, manifest, *fixed = map(Path, sys.argv[1:])
paths = fixed + [decoder, flags]
flag_values = json.loads(flags.read_text())
search_directories = []
for token in flag_values["nf_libs"]:
    if token.startswith("-L") and len(token) > 2:
        search_directories.append(Path(token[2:]))
for token in flag_values["nf_libs"]:
    if not token.startswith("-l") or len(token) <= 2:
        continue
    library_name = token[2:]
    candidates = []
    for directory in search_directories:
        candidates.extend((directory / f"lib{library_name}.so", directory / f"lib{library_name}.a"))
    resolved = next((candidate for candidate in candidates if candidate.is_file()), None)
    if resolved is not None:
        paths.append(resolved.resolve())
runtime = subprocess.run(["ldd", "-r", str(decoder)], check=True, capture_output=True, text=True)
for line in runtime.stdout.splitlines():
    match = re.search(r"=>\s+(/\S+)", line)
    if match:
        paths.append(Path(match.group(1)))
    elif line.startswith("/"):
        paths.append(Path(line.split()[0]))
unique = sorted({path.resolve() for path in paths if path.is_file()}, key=str)
with manifest.open("w") as stream:
    for path in unique:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stream.write(f"{digest}  {path}\n")
PY

cd "$repo_root"
if ! python3 "$validator" --raw-root "$raw_root" --timestamp "$raw_timestamp" \
    --snapshot-root "$snapshot_root" --snapshot-manifest "$input_manifest"; then
  write_failure 'raw input snapshot failed' 1
  exit 1
fi
# The decoder is confined to stage_root for writes. The snapshot is immutable
# after its exact source bytes and time metadata have been recorded.
chmod -R a-w "$snapshot_root"

if ! python3 - "$input_manifest" "$probe_root" "$probe_manifest" <<'PY'
import hashlib
import json
import shutil
import sys
from pathlib import Path

import netCDF4

manifest_path, probe_root, probe_manifest = map(Path, sys.argv[1:])
manifest = json.loads(manifest_path.read_text())
probe_root.mkdir()
source = next(item for item in manifest["files"] if item["source_path"].split("/")[-1].startswith("RDR_GSN_"))
origin = source["time_contract"]["origin_epoch"]
cases = []
for name, expected in (
    ("malformed_sweep_index", 2),
    ("nonzero_add_offset", 0),
    ("mismatched_time_origin", 2),
    ("unsupported_time_calendar", 2),
    ("unsupported_time_units", 2),
):
    case_root = probe_root / name
    case_root.mkdir()
    fixture = case_root / "RDR_GSN_FQC_202608162200.nc"
    shutil.copyfile(source["snapshot_path"], fixture)
    with netCDF4.Dataset(fixture, "r+") as dataset:
        if name == "malformed_sweep_index":
            dataset.variables["sweep_start_ray_index"][0] += 1
        elif name == "nonzero_add_offset":
            dataset.variables["DBZH"].setncattr("add_offset", 1.5)
            dataset.variables["VELH"].setncattr("add_offset", -2.25)
            dataset.variables["WIDTHH"].setncattr("add_offset", 0.75)
        elif name == "mismatched_time_origin":
            dataset.variables["time"].setncattr(
                "units", "seconds since 2026-08-16T14:00:01Z"
            )
        elif name == "unsupported_time_calendar":
            dataset.variables["time"].setncattr("calendar", "360_day")
        else:
            dataset.variables["time"].setncattr(
                "units", "minutes since 2026-08-16T13:00:01Z"
            )
    fixture.chmod(0o440)
    cases.append({
        "name": name,
        "fixture": str(fixture),
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "radar_name": "GSN",
        "epoch": origin,
        "juldate": source["time_contract"]["juldate"],
        "expected_status": expected,
        "output_root": str(case_root / "output"),
        "log": str(case_root / "decoder.log"),
        "validation_log": str(case_root / "validation.log"),
    })
iia_source = next(
    (item for item in manifest["files"] if item["source_path"].split("/")[-1].startswith("RDR_IIA_")),
    None,
)
if iia_source is not None:
    case_root = Path(probe_root) / "iia_wrong_13z_origin"
    case_root.mkdir()
    fixture = case_root / "RDR_IIA_FQC_202608162200.nc"
    shutil.copyfile(iia_source["snapshot_path"], fixture)
    fixture.chmod(0o440)
    cases.append({
        "name": "iia_wrong_13z_origin",
        "fixture": str(fixture),
        "fixture_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
        "radar_name": "IIA",
        "epoch": origin,
        "juldate": source["time_contract"]["juldate"],
        "expected_status": 2,
        "output_root": str(case_root / "output"),
        "log": str(case_root / "decoder.log"),
        "validation_log": str(case_root / "validation.log"),
    })
Path(probe_manifest).write_text(json.dumps({"schema": 1, "cases": cases}, indent=2, sort_keys=True) + "\n")
PY
then
  write_failure 'probe fixture generation failed' 1
  exit 1
fi

mapfile -t case_records < <(python3 - "$input_manifest" <<'PY'
import json
import sys

manifest = json.load(open(sys.argv[1]))
for item in manifest["files"]:
    contract = item["time_contract"]
    name = item["source_path"].rsplit("/", 1)[-1]
    print(f"{item['snapshot_path']}\t{name}\t{contract['origin_epoch']:.17g}\t{contract['juldate']}")
PY
)

for record in "${case_records[@]}"; do
  IFS=$'\t' read -r raw_path raw_name file_epoch file_juldate <<<"$record"
  radar_name=${raw_name#RDR_}
  radar_name=${radar_name%%_FQC_*}
  mkdir -p "$stage_root/RADR/ouda/$radar_name"
  case_log="$stage_root/${radar_name}.decoder.log"
  set +e
  JULDATE="$file_juldate" EPODATE="$file_epoch" RDRNAME="$radar_name" NC_DAOU="$stage_root" \
    python3 "$repo_root/tools/landlock_run.py" "$stage_root" \
      python3 "$repo_root/tools/run_bound_executable.py" \
      --sha256-file "$build_root/executable.sha256" "$build_root/decoder" -- \
      "$raw_path" >"$case_log" 2>&1
  status=$?
  set -e
  if [[ $status -ne 0 ]]; then
    write_failure "decoder failed for $raw_name" "$status"
    printf 'decoder failed for %s (status %s); stage=%s\n' "$raw_name" "$status" "$stage_root" >&2
    sed -n '1,160p' "$case_log" >&2
    exit "$status"
  fi
done

if ! python3 "$validator" --raw-root "$snapshot_root" --output-root "$stage_root" \
    --timestamp "$raw_timestamp" >"$stage_root/validation.log" 2>&1; then
  write_failure "per-radar output validation failed" 1
  cat "$stage_root/validation.log" >&2
  exit 1
fi
cat "$stage_root/validation.log"

probe_records=$(python3 - "$probe_manifest" <<'PY'
import json
import sys
for item in json.load(open(sys.argv[1]))["cases"]:
    print("\t".join((item["name"], item["fixture"], str(item["epoch"]), item["juldate"], str(item["expected_status"]), item["output_root"], item["log"])))
PY
)
while IFS=$'\t' read -r probe_name fixture probe_epoch probe_juldate expected probe_output probe_log; do
  [[ -n $probe_name ]] || continue
  mkdir -p "$probe_output/RADR/ouda/GSN"
  set +e
  JULDATE="$probe_juldate" EPODATE="$probe_epoch" RDRNAME=GSN NC_DAOU="$probe_output" \
    python3 "$repo_root/tools/landlock_run.py" "$probe_output" \
      python3 "$repo_root/tools/run_bound_executable.py" \
      --sha256-file "$build_root/executable.sha256" "$build_root/decoder" -- \
      "$fixture" >"$probe_log" 2>&1
  status=$?
  set -e
  printf '%s\n' "$status" >"${probe_log%.log}.exit_status"
  if [[ $status -ne $expected ]]; then
    write_failure "probe $probe_name returned $status, expected $expected" "$status"
    cat "$probe_log" >&2
    exit "$status"
  fi
  if [[ $expected -ne 0 ]] && find "$probe_output" -type f -name '*_elev*' -print -quit | rg -q .; then
    write_failure "rejected probe $probe_name left an output product" 1
    exit 1
  fi
  if [[ $expected -eq 0 ]]; then
    if ! python3 "$validator" --raw-root "$(dirname "$fixture")" --output-root "$probe_output" \
        --timestamp "$raw_timestamp" >"${probe_log%/*}/validation.log" 2>&1; then
      write_failure "accepted probe $probe_name failed output validation" 1
      cat "${probe_log%/*}/validation.log" >&2
      exit 1
    fi
  fi
done <<<"$probe_records"

cp "$input_manifest" "$stage_root/input_manifest.json"
cp "$probe_manifest" "$stage_root/probe_manifest.json"
cp "$build_root/build_inputs.sha256" "$stage_root/build_inputs.sha256"
cp "$build_root/build_flags.json" "$stage_root/build_flags.json"
cp "$build_root/runtime.log" "$stage_root/runtime.log"
python3 - "$stage_root/receipt.json" "$stage_root" "$published_root" "$input_manifest" \
  "$probe_manifest" "$build_root" "$raw_root" "$raw_timestamp" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

receipt_path, stage_root, published_root, input_manifest, probe_manifest, build_root, raw_root, cycle = map(Path, sys.argv[1:])
inputs = json.loads(input_manifest.read_text())
probes = json.loads(probe_manifest.read_text())
products = {}
for path in sorted((stage_root / "RADR").rglob("*_elev*")):
    products[str(path.relative_to(stage_root))] = hashlib.sha256(path.read_bytes()).hexdigest()
receipt = {
    "schema": 2,
    "status": "PASS",
    "requested_cycle": cycle.name,
    "raw_root": str(raw_root),
    "input_manifest": "input_manifest.json",
    "inputs": inputs["files"],
    "build_root": str(build_root),
    "build_inputs_sha256": str(build_root / "build_inputs.sha256"),
    "build_flags_json": str(build_root / "build_flags.json"),
    "published_output_root": str(published_root),
    "output_products": products,
    "probe_manifest": probes,
    "scope": "RAW_INPUT_ONLY; raw moments only; no dealiasing, fall-speed correction, QC, remapping, or target authority",
}
receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
PY

set +e
python3 - "$stage_root" "$published_root" <<'PY'
import ctypes
import errno
import os
import sys
from pathlib import Path

source, destination = map(Path, sys.argv[1:])
source_parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
destination_parent = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    renameat2 = getattr(ctypes.CDLL(None, use_errno=True), "renameat2", None)
    if renameat2 is None:
        raise OSError(errno.ENOSYS, "renameat2 is unavailable")
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    if renameat2(source_parent, os.fsencode(source.name), destination_parent, os.fsencode(destination.name), 1) != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    os.fsync(source_parent)
    os.fsync(destination_parent)
finally:
    os.close(destination_parent)
    os.close(source_parent)
PY
publish_status=$?
set -e
if [[ $publish_status -ne 0 ]]; then
  write_failure 'atomic final publication failed; private stage retained' "$publish_status"
  printf 'atomic final publication failed; stage=%s\n' "$stage_root" >&2
  exit "$publish_status"
fi

printf 'RADAR_DECODER_RUN_PASS build=%s output=%s receipt=%s\n' \
  "$build_root" "$published_root" "$published_root/receipt.json"
