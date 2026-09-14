#!/usr/bin/env bash
set -euo pipefail

script_dir=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$script_dir/.." && pwd)
workspace=$(dirname "$repo")
source_root="$workspace/klaps-v5.0_/src"
isolated="$repo/src/upstream/radar/remap"
common="${CLOUD_BAL_REMAP_COMMON_BUILD:-$repo/scratch/upstream_wind_openmp_build.e76MLf}"

if [[ "${1:-}" == "--common-build" ]]; then
    [[ $# -eq 2 ]] || { echo "Usage: $0 [--common-build PATH]" >&2; exit 2; }
    common=$2
fi
common=$(cd "$common" && pwd)

. "$repo/tests/intel_toolchain.sh"

# Reuse the parent-verified common archive, but verify every recorded input
# (including the producer builder) and runtime dependency before linking.
sha256sum -c "$common/inputs.sha256"
sha256sum -c "$common/runtime.sha256"

nf_config="$workspace/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
read -r -a nf_flags <<<"$($nf_config --fflags)"
read -r -a nf_libs <<<"$($nf_config --flibs)"

build=$(mktemp -d "$repo/scratch/radar_remap_build.XXXXXX")
printf '%s\n' "$build" > "$repo/scratch/radar_remap_build.path"
printf '%s\n' "$common" > "$build/common_build.path"
sha256sum "$common/libcommon.a" > "$build/common_archive.sha256"
exec > "$build/build.log" 2>&1

cd "$build"
mkdir sources
cp "$source_root/ingest/radar/remap/"*.f sources/
for name in fill_common get_azimuths_deg get_scandata ld_ray lut_gen \
            rcptoremote readdata ref_fill_horz timconv; do
    cp "$source_root/lib/radar/remap_ftn/$name.f" sources/
done

# Overlay only the reviewed consumer corrections.  Operational sources remain
# the fallback for files that are outside this focused patch.
cp "$isolated/"*.f sources/
if compgen -G "$isolated/*.cmn" >/dev/null; then
    cp "$isolated/"*.cmn sources/
fi
if compgen -G "$isolated/*.inc" >/dev/null; then
    cp "$isolated/"*.inc sources/
fi

cp "$script_dir/build_radar_remap.sh" build.executed.sh
{
    sha256sum "$common/libcommon.a" "$common/inputs.sha256" \
        "$common/runtime.sha256" "$nf_config" "$CLOUD_BAL_FC" \
        "$script_dir/build_radar_remap.sh" \
        "$repo/tools/landlock_run.py" "$repo/tools/run_bound_executable.py" \
        "$script_dir/intel_toolchain.sh"
    find "$source_root/include" -type f -exec sha256sum {} +
    sha256sum "$isolated/"*.f "$isolated/"*.cmn "$isolated/"*.inc \
        "$isolated/cdl/v00.cdl"
    sha256sum sources/*.f sources/*.cmn sources/*.inc
} > inputs.sha256

flags=("${CLOUD_BAL_FIXED_72_FLAGS[@]}" -convert big_endian \
    -align dcommons -assume byterecl -qopenmp \
    -I "$build/sources" -I "$source_root/include" -I "$source_root/lib" "${nf_flags[@]}")

for source in sources/*.f; do
    "$CLOUD_BAL_FC" "${flags[@]}" -c "$source" \
        -o "$(basename "${source%.f}").o"
done

"$CLOUD_BAL_FC" "${flags[@]}" ./*.o "$common/libcommon.a" \
    "${nf_libs[@]}" -Wl,-Map,link.map -o klps_radr_ingt.exe

ldd -r klps_radr_ingt.exe > runtime.log 2>&1
if rg 'not found|undefined symbol:' runtime.log; then
    exit 1
fi

mapfile -t runtime_files < <(awk '$2=="=>" && $3 ~ /^\// {print $3} $1 ~ /^\// {print $1}' \
                             runtime.log | sort -u)
[[ ${#runtime_files[@]} -gt 0 ]]
sha256sum "${runtime_files[@]}" > runtime.sha256
sha256sum "$repo/tools/landlock_run.py" "$repo/tools/run_bound_executable.py" \
    "$script_dir/intel_toolchain.sh" > launcher.sha256

sha256sum -c inputs.sha256
sha256sum -c runtime.sha256
sha256sum -c launcher.sha256
sha256sum klps_radr_ingt.exe > executable.sha256
printf 'PINNED_IFX_REMAP_LINK_PASS\n'
