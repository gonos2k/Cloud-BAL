#!/usr/bin/env bash
# Complete serial WPS build. WRF/NetCDF libraries are pinned prebuilt inputs.
set -euo pipefail
repo=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
if [[ $# != 6 ]]; then
  echo 'usage: build_qbal_full_metgrid.sh WPS_ROOT BUILD_ROOT O0|O2 WRF_ROOT NETCDF_ROOT PATCH' >&2
  exit 2
fi
wps=$(realpath -e "$1")
build=$(realpath -m "$2")
level=$3
wrf=$(realpath -e "$4")
netcdf=$(realpath -e "$5")
patch_file=$(realpath -e "$6")
[[ ! -e $build && ! -L $build ]] || { echo 'existing build root rejected' >&2; exit 2; }
source_pins="$repo/tests/wps_full_sources.sha256"
link_pins="$repo/tests/wps_link_inputs.sha256"
. "$repo/tests/intel_toolchain.sh"
unset F_UFMTENDIAN
case $level in
  O0) flags=("${CLOUD_BAL_FREE_FLAGS[@]}");;
  O2) flags=("${CLOUD_BAL_REPRO_FLAGS[@]}");;
  *) echo 'expected O0 or O2' >&2; exit 2;;
esac
cc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/icx
[[ $(sha256sum "$cc" | cut -d' ' -f1) == 9fe05a4aef59abce8d8f0631964dd0f12932345d0d38fc9e9d6f6af844e94b33 ]]
[[ $(git -C "$wps" rev-parse HEAD) == 335c76a111f84503e8b963abaf273ea8053645bb ]]
(cd "$wps" && sha256sum -c "$source_pins")
sha256sum -c "$link_pins"

wrf_objects=(frame/module_driver_constants.o frame/pack_utils.o frame/module_machine.o frame/module_internal_header_util.o)
wrf_archives=(external/io_grib1/libio_grib1.a external/io_grib_share/libio_grib_share.a external/io_int/libwrfio_int.a external/io_netcdf/libwrfio_nf.a)
# Require exactly the pinned installation's inputs, not just equal filenames.
link_inputs=()
for name in "${wrf_objects[@]}" "${wrf_archives[@]}" inc/wrf_io_flags.h inc/wrf_status_codes.h external/io_int/module_internal_header_util.mod; do
  link_inputs+=("$wrf/$name")
done
for name in include/netcdf.inc include/netcdf.mod lib/libnetcdff.a lib/libnetcdf.a; do
  link_inputs+=("$netcdf/$name")
done
cmp <(sha256sum "${link_inputs[@]}") <(awk '/^# Runtime closure/{exit} !/^#/{print}' "$link_pins")
mkdir -p "$build/objects" "$build/WPS/metgrid/src"
cp "$wrf/external/io_int/module_internal_header_util.mod" "$build/objects/"
exec > >(tee "$build/build.log") 2>&1
printf 'wps_commit=335c76a111f84503e8b963abaf273ea8053645bb\nlevel=%s\n' "$level" > "$build/build_config.txt"
sha256sum "$CLOUD_BAL_FC" "$cc" /lib/cpp "$cloud_bal_imf" "$cloud_bal_intlc" "$cloud_bal_setvars" \
  "$repo/tests/intel_toolchain.sh" "$repo/tests/build_qbal_full_metgrid.sh" \
  "$source_pins" "$link_pins" "$patch_file" > "$build/build_inputs.sha256"

# One ordered list governs source verification, copying, compilation and linking.
sources=()
objects=()
while read -r expected name; do
  sources+=("$build/WPS/$name")
  filename=${name##*/}
  objects+=("${filename%.*}.o")
  cp -L "$wps/$name" "$build/WPS/$name"
done < "$source_pins"
(cd "$build/WPS" && sha256sum -c "$source_pins")
patch -d "$build" -p1 < "$patch_file"
sha256sum "${sources[@]}" > "$build/patched_sources.sha256"
cd "$build/objects"
pwd -P > "$build/build.cwd"
record_argv() {
  python3 - "$@" >> "$build/compiler_argv.jsonl" <<'PY'
import json, sys
print(json.dumps(sys.argv[1:]))
PY
  "$@"
}
cpp_flags=(-P -traditional -D_UNDERSCORE -DBYTESWAP -DLINUX -DIO_NETCDF -DIO_BINARY -DIO_GRIB1 \
  -DBIT32 -D_METGRID -DUSE_JPEG2000 -DUSE_PNG -I"$wrf/inc" -I"$netcdf/include")
for index in "${!sources[@]}"; do
  source=${sources[index]}
  object=${objects[index]}
  if [[ $source == *.c ]]; then
    record_argv "$cc" -"$level" "${cpp_flags[@]:2}" -c "$source" -o "$object"
  else
    preprocessed=${object%.o}.f90
    record_argv /lib/cpp "${cpp_flags[@]}" "$source" > "$preprocessed"
    record_argv "$CLOUD_BAL_FC" "${flags[@]}" -free -convert little_endian \
      -I "$build/objects" -I "$netcdf/include" -c "$preprocessed" -o "$object"
  fi
done
linked=()
for name in "${wrf_objects[@]}" "${wrf_archives[@]}"; do linked+=("$wrf/$name"); done
linked+=("$netcdf/lib/libnetcdff.a" "$netcdf/lib/libnetcdf.a")
record_argv "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian \
  "${objects[@]}" "${linked[@]}" -o "$build/metgrid.exe"

# Keep every other object identical in the original-time-selection control.
mkdir "$build/unpatched_mod"
record_argv /lib/cpp "${cpp_flags[@]}" "$wps/metgrid/src/process_domain_module.F" > process_domain_unpatched.f90
record_argv "$CLOUD_BAL_FC" "${flags[@]}" -free -convert little_endian \
  -I "$build/objects" -I "$netcdf/include" -module "$build/unpatched_mod" \
  -c process_domain_unpatched.f90 -o process_domain_unpatched.o
control_objects=()
for object in "${objects[@]}"; do
  if [[ $object == process_domain_module.o ]]; then control_objects+=(process_domain_unpatched.o)
  else control_objects+=("$object"); fi
done
record_argv "$CLOUD_BAL_FC" "${flags[@]}" -convert little_endian \
  "${control_objects[@]}" "${linked[@]}" -o "$build/unpatched_metgrid.exe"

ldd -r "$build/metgrid.exe" > "$build/runtime.log" 2>&1
if rg 'not found|undefined symbol:' "$build/runtime.log"; then exit 1; fi
mapfile -t runtime < <(awk '$2=="=>" && $3 ~ /^\// {print $3} $1 ~ /^\// {print $1}' "$build/runtime.log" | sort -u)
sha256sum "${link_inputs[@]}" "${runtime[@]}" > "$build/link_inputs.sha256"
cmp "$build/link_inputs.sha256" <(sed '/^#/d' "$link_pins")
sha256sum -c "$link_pins"
(cd "$wps" && sha256sum -c "$source_pins")
sha256sum -c "$build/patched_sources.sha256"
sha256sum -c "$build/build_inputs.sha256"
sha256sum "$build/metgrid.exe" "$build/unpatched_metgrid.exe" > "$build/executables.sha256"
printf 'PINNED_IFX_FULL_METGRID_%s_PASS\n' "$level"
