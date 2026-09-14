#!/usr/bin/env bash
# Build one current KLAPS stage in scratch; never run or install.
set -euo pipefail
repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
source_root="$workspace_root/klaps-v5.0_/src"
producer=${1:-temperature}
optimization=${2:-O0}
[[ $# -le 2 ]] || { echo 'Usage: bash build_upstream_producer.sh [temperature|surface|humidity|derived|cloud|wind_openmp|balance|lapsprep] [O0|O2]' >&2; exit 2; }
case "$optimization" in
  O0|O2) ;;
  *) echo "Unsupported optimization: $optimization (expected O0 or O2)" >&2; exit 2 ;;
esac
libraries=(common temp mthermo)
case "$producer" in
  temperature)
    main_source="$repo_root/src/temp/puttmpanal_drv.f"
    executable=klps_anal_temp.exe ;;
  surface)
    main_source="$repo_root/src/sfc/laps_sfc.f"
    executable=klps_anal_lsfc.exe
    libraries+=(util sfc) ;;
  humidity)
    main_source="$repo_root/src/humid/lq3driver.f"
    executable=klps_anal_humd.exe
    libraries=(common fm powell opt90 mthermo humid) ;;
  derived)
    main_source="$repo_root/src/upstream/laps_deriv.f"
    executable=klps_anal_derv.exe
    libraries=(common mthermo util deriv) ;;
  cloud)
    main_source="$repo_root/src/upstream/laps_cloud.f"
    executable=klps_anal_clod.exe
    libraries=(common fm mthermo util goeslib cloud) ;;
  wind_openmp)
    main_source="$repo_root/src/upstream/wind_openmp/main.f"
    executable=klps_anal_wind_openmp.exe
    # Match native precedence: OpenMP Barnes must precede common serial Barnes.
    libraries=(wind_openmp common) ;;
  balance)
    main_source="$repo_root/src/balance/qbalpe.f"
    executable=klps_anal_qbal.exe
    libraries=(bgdata common util mthermo balance) ;;
  lapsprep)
    main_source="$repo_root/src/lapsprep/lapsprep.f90"
    executable=klps_anal_prep.exe
    libraries=(common mthermo modules lapsprep) ;;
  *) echo "Unsupported producer: $producer" >&2; exit 2 ;;
esac
producer_openmp=false
case "$producer" in
  temperature|surface|wind_openmp) producer_openmp=true ;;
esac
. "$repo_root/tests/intel_toolchain.sh"
cc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/icx
[[ $(sha256sum "$cc" | cut -d' ' -f1) == 9fe05a4aef59abce8d8f0631964dd0f12932345d0d38fc9e9d6f6af844e94b33 ]]
nf_config="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-fortran-ifx/install/bin/nf-config"
[[ $(sha256sum "$nf_config" | cut -d' ' -f1) == e39004b972304d63c1b46fb065db754718d571430063819ddafdd7bd3612d8a5 ]]
read -r -a nf_flags <<<"$("$nf_config" --fflags)"
read -r -a nf_libs <<<"$("$nf_config" --flibs)"
nc_include="$workspace_root/klaps-v5.0_/baseline/20260818_rdr_input/deps/netcdf-c-gcc/install/include"
netcdff_archive="$(dirname "$(dirname "$nf_config")")/lib/libnetcdff.a"
netcdf_archive="$(dirname "$nc_include")/lib/libnetcdf.a"
[[ $(sha256sum "$netcdff_archive" | cut -d' ' -f1) == f610d7ebedf48d17023e9b8377d74d93542bde40d091ec7a5518bb30d17c8a39 ]]
[[ $(sha256sum "$netcdf_archive" | cut -d' ' -f1) == f603197dafe9397e682cd84dd699ca22ac24188053f8b9b1afd1d07e5985c288 ]]
build_dir=$(mktemp -d "$repo_root/scratch/upstream_${producer}_build.XXXXXX")
printf '%s\n' "$build_dir"
mkdir "$build_dir/main"
# GNU89 denotes the legacy C dialect, not a GNU compiler fallback.
f_flags=("-$optimization" -g -traceback -fpe0 -fp-model strict -fixed -extend-source 72
         -convert big_endian -align dcommons -assume byterecl
         -I "$build_dir/common" -I "$source_root/include"
         -I "$source_root/lib" "${nf_flags[@]}")
c_flags=("-$optimization" -g -std=gnu89 -DLITTLE -DSWAPBYTE -DFORTRANUNDERSCORE
         -I "$source_root/include" -I "$nc_include")
sources=()
if [[ $producer == derived || $producer == balance || $producer == lapsprep ]]; then
  # State-carrying adapters share one explicitly ordered module dependency chain.
  for module in cloud_bal_field_contracts cloud_bal_moisture cloud_bal_state \
                cloud_bal_grid_geometry cloud_bal_column_physics \
                cloud_bal_balance_operator cloud_bal_pipeline cloud_bal_real_netcdf \
                cloud_bal_stage_payload cloud_bal_stage_context; do
    sources+=("$repo_root/src/common/$module.f90")
  done
  case "$producer" in
    derived) adapter=deriv ;;
    balance) adapter=balance ;;
    lapsprep) adapter=lapsprep ;;
  esac
  sources+=("$repo_root/src/common/cloud_bal_${adapter}_adapter.f90")
fi
makefiles=()
[[ $producer != temperature ]] || makefiles+=("$source_root/temp/Makefile")
for library in "${libraries[@]}"; do
  mkdir "$build_dir/$library"
  directory="$source_root/lib/$library"
  [[ $library != common ]] || directory="$source_root/lib"
  [[ $library != sfc ]] || directory="$source_root/sfc"
  [[ $library != humid ]] || directory="$source_root/humid"
  [[ $library != deriv ]] || directory="$source_root/deriv"
  [[ $library != cloud ]] || directory="$source_root/cloud"
  [[ $library != wind_openmp ]] || directory="$source_root/wind_openmp"
  [[ $library != balance ]] || directory="$source_root/balance"
  [[ $library != lapsprep ]] || directory="$source_root/lapsprep"
  makefiles+=("$directory/Makefile")
  mapfile -t names < <(sed -n '/^SRC[[:space:]]*=/,/^$/p' "$directory/Makefile" |
                     rg -o '[A-Za-z0-9_-]+\.(f90|f|F|c)\b')
  if [[ $library == modules || $library == lapsprep ]]; then
    mapfile -t names < <(sed -n '/^FMOD[[:space:]]*=/,/^$/p' "$directory/Makefile" |
                        rg -o '[A-Za-z0-9_-]+\.o\b' | sed 's/\.o$/.f90/')
    if [[ $library == modules ]]; then
      ordered=(module_horiz_interp module_map_utils module_grib module_mm5v3_io
               module_time_utils module_vinterp_utils module_wrfsi_static
               module_grid_utils module_wrf_netcdf)
    else
      ordered=(module_constants module_date_pack module_setup module_laps_static
               module_lapsprep_mm5 module_lapsprep_rams module_lapsprep_wrf
               module_lapsprep_wps module_lapsprep_netcdf)
      sources+=("$repo_root/src/common/cloud_bal_pressure_analysis.f90"
                "$repo_root/src/common/cloud_bal_wps_adapter.f90")
    fi
    ordered=("${ordered[@]/%/.f90}")
    diff <(printf '%s\n' "${names[@]}" | sort -u) \
         <(printf '%s\n' "${ordered[@]}" | sort)
    names=("${ordered[@]}")
    if [[ $library == lapsprep ]]; then
      mapfile -t helpers < <(sed -n '/^FSRC[[:space:]]*=/,/^$/p' "$directory/Makefile" |
                            rg -o '[A-Za-z0-9_-]+\.f90\b')
      names+=("${helpers[@]}")
    fi
  fi
  [[ ${#names[@]} -gt 0 ]]
  if [[ $library == opt90 ]]; then
    # Explicit module order from opt90/Makefile dependencies; no stale .mod files.
    ordered=(type_kinds file_utility error_handler parameters coefficient_utility
             transmittance_coefficients spectral_coefficients absorber_profile
             predictors transmittance sensor_planck_routines radiance initialize
             forward_model optran90_fm)
    ordered=("${ordered[@]/%/.f90}")
    diff <(printf '%s\n' "${names[@]}" | sort -u) \
         <(printf '%s\n' "${ordered[@]}" | sort)
    names=("${ordered[@]}")
  fi
  for name in "${names[@]}"; do
    input="$directory/$name"
    if [[ $producer == surface && $library == common && $name == read_surface_obs.f ]]; then
      input="$repo_root/src/upstream/read_surface_obs.f"
    fi
    if [[ $producer == surface && $library == common && $name == read_surface.f ]]; then
      input="$repo_root/src/upstream/read_surface.f"
    fi
    if [[ $producer == surface && $library == sfc && $name == qc_data.f ]]; then
      input="$repo_root/src/sfc/qc_data.f"
    fi
    if [[ $library == deriv && ( $name == laps_deriv.f || $name == laps_deriv_sub.f ) ]]; then
      input="$repo_root/src/upstream/$name"
    fi
    if [[ $producer == derived && $library == common && $name == get_cloud_deriv.f ]]; then
      input="$repo_root/src/upstream/$name"
    fi
    if [[ $library == cloud && ( $name == laps_cloud.f || $name == laps_cloud_sub.f ) ]]; then
      input="$repo_root/src/upstream/$name"
    fi
    if [[ $library == wind_openmp && ( $name == main_sub.f || $name == barnes_multivariate.f90 ) ]]; then
      input="$repo_root/src/upstream/wind_openmp/$name"
    fi
    if [[ $library == balance && $name == writeballaps.f ]]; then
      input="$repo_root/src/balance/$name"
    fi
    if [[ $producer == balance && $library == bgdata && $name == lapsio.f ]]; then
      input="$repo_root/src/lib/bgdata/$name"
    fi
    if [[ $library == lapsprep ]]; then
      case "$name" in
        lapsprep.f90|module_setup.f90|module_laps_static.f90|module_lapsprep_wps.f90|lwc2vapor.f90|ice2vapor.f90|saturate_lwc_points.f90|saturate_ice_points.f90)
          input="$repo_root/src/lapsprep/$name" ;;
      esac
    fi
    # Executable Makefiles may include the main in SRC; link it only once.
    [[ "$input" != "$main_source" ]] || continue
    if [[ $library == sfc && $name == lapsvanl.f ]]; then
      input="$repo_root/src/sfc/lapsvanl.f"
    fi
    sources+=("$input")
  done
done
if [[ $producer == balance ]]; then
  # Explicit USE order; modules and legacy main share the fresh module directory.
  sources+=("$repo_root/src/common/cloud_bal_localization.f90"
            "$repo_root/src/common/cloud_bal_wind_modes.f90")
fi
if [[ $producer == derived ]]; then
  sources+=("$repo_root/tools/cloud_bal_ncgen_system.c")
fi
sources+=("$main_source")
# Record input bytes before compilation. Includes are small; cover the complete
# include directory rather than infer a partial transitive include list.
mapfile -t includes < <(find "$source_root/include" "$nc_include" \
  "$(dirname "$(dirname "$nf_config")")/include" -maxdepth 1 -type f | sort)
sha256sum "${sources[@]}" "${includes[@]}" "$cc" "$CLOUD_BAL_FC" "$nf_config" \
  "$netcdff_archive" "$netcdf_archive" "$nc_include/netcdf.h" \
  "$(dirname "$(dirname "$nf_config")")/include/netcdf.inc" \
  "${makefiles[@]}" \
  "$repo_root/tools/build_upstream_producer.sh" "$repo_root/tools/pin_link_inputs.py" \
  "$repo_root/tools/build_audited_upstream.py" "$repo_root/tools/pin_compiler_inputs.py" \
  "$repo_root/tests/intel_toolchain.sh" \
  "$cloud_bal_setvars" "$cloud_bal_imf" "$cloud_bal_intlc" \
  > "$build_dir/inputs.sha256"
# An audited discovery build supplies these bytes before this fresh compilation.
# The ordinary builder alone does not claim compiler-process input closure.
if [[ -n ${CLOUD_BAL_COMPILER_INPUTS_MANIFEST:-} ]]; then
  [[ -f $CLOUD_BAL_COMPILER_INPUTS_MANIFEST && -s $CLOUD_BAL_COMPILER_INPUTS_MANIFEST && \
     ! -L $CLOUD_BAL_COMPILER_INPUTS_MANIFEST ]]
  cp "$CLOUD_BAL_COMPILER_INPUTS_MANIFEST" "$build_dir/compiler_inputs.sha256"
  sha256sum -c --strict "$build_dir/compiler_inputs.sha256" \
    > "$build_dir/compiler_inputs.precheck.log"
  cat "$build_dir/compiler_inputs.sha256" >> "$build_dir/inputs.sha256"
  sha256sum "$build_dir/compiler_inputs.sha256" >> "$build_dir/inputs.sha256"
fi
{
  # Do not search the caller's working directory for stale Fortran modules.
  cd "$build_dir"
  set -x
  printf 'IFX %q\nICX %q\n' "$CLOUD_BAL_FC" "$cc"
  printf 'OPTIMIZATION %s\n' "$optimization"
  printf 'Fortran options: '; printf '%q ' "${f_flags[@]}"; printf '\n'
  printf 'OpenMP: temperature/surface main, src/sfc and wind_openmp; other sources serial\n'
  printf 'C options: '; printf '%q ' "${c_flags[@]}"; printf '\n'
  for input in "${sources[@]}"; do
    name=$(basename "$input")
    case "$input" in
      */lib/temp/*) library=temp ;;
      */lib/mthermo/*) library=mthermo ;;
      */lib/util/*) library=util ;;
      */lib/fm/*) library=fm ;;
      */lib/powell/*) library=powell ;;
      */lib/opt90/*) library=opt90 ;;
      */lib/goeslib/*) library=goeslib ;;
      */lib/bgdata/*) library=bgdata ;;
      */lib/modules/*) library=modules ;;
      */balance/*) library=balance ;;
      */lapsprep/*) library=lapsprep ;;
      */sfc/*) library=sfc ;;
      */humid/*) library=humid ;;
      */deriv/*) library=deriv ;;
      */upstream/laps_cloud*) library=cloud ;;
      */upstream/laps_deriv*) library=deriv ;;
      */cloud/*) library=cloud ;;
      */wind_openmp/*) library=wind_openmp ;;
      *) library=common ;;
    esac
    [[ "$input" != "$main_source" ]] || library=main
    output="$build_dir/$library/${name%.*}.o"
    compile_flags=("${f_flags[@]}")
    # Producer Makefiles use OpenMP; their library Makefiles do not.
    if [[ $library == sfc || $library == wind_openmp ]] ||
       [[ $library == main && $producer_openmp == true ]]; then
      compile_flags+=(-qopenmp)
    fi
    printf 'COMPILE %s\n' "$input"
    if [[ $name == *.c ]]; then
      c_extra=()
      if [[ $producer == derived && $name == rwl_v3.c ]]; then
        c_extra=(-Dsystem=cloud_bal_ncgen_system)
      fi
      "$cc" -c "${c_flags[@]}" "${c_extra[@]}" "$input" -o "$output"
    elif [[ $name == *.f90 ]]; then
      "$CLOUD_BAL_FC" -c "${compile_flags[@]}" -free \
        -module "$build_dir/common" "$input" -o "$output"
    elif [[ $name == *.F ]]; then
      "$CLOUD_BAL_FC" -c "${compile_flags[@]}" -fpp -Dx86_64 -DF90 -DFORTRANUNDERSCORE -DDYNAMIC \
        -module "$build_dir/common" "$input" -o "$output"
    else
      "$CLOUD_BAL_FC" -c "${compile_flags[@]}" -module "$build_dir/common" "$input" -o "$output"
    fi
  done
  # The main program is not part of a library.
  driver="$build_dir/main/$(basename "${main_source%.*}").o"
  archives=()
  for library in "${libraries[@]}"; do
    ar crs "$build_dir/lib$library.a" "$build_dir/$library/"*.o
    archives+=("$build_dir/lib$library.a")
  done
  link_flags=()
  if [[ $producer_openmp == true ]]; then
    link_flags+=(-qopenmp)
  fi
  link_stage() {
    "$CLOUD_BAL_FC" "${link_flags[@]}" "$driver" -Wl,--start-group "${archives[@]}" \
      -Wl,--end-group "${nf_libs[@]}" "-Wl,-Map,$build_dir/link.map" -o "$build_dir/$executable"
  }
  # Discover implicit startup/static-library inputs, then pin them BEFORE the
  # accepted final link. Preserve the original pre-compilation manifest too.
  link_stage
  cp "$build_dir/inputs.sha256" "$build_dir/compile_inputs.sha256"
  cp "$build_dir/link.map" "$build_dir/discovery_link.map"
  python3 "$repo_root/tools/pin_link_inputs.py" "$build_dir/link.map" "$build_dir/link_inputs.sha256"
  cat "$build_dir/link_inputs.sha256" >> "$build_dir/inputs.sha256"
  link_stage
  python3 "$repo_root/tools/pin_link_inputs.py" "$build_dir/link.map" "$build_dir/link_inputs.sha256" --verify
  if [[ $producer == wind_openmp ]]; then
    rg -Fq 'libwind_openmp.a(barnes_multivariate.o)' "$build_dir/link.map"
    if rg -F 'libcommon.a(barnes_multivariate.o)' "$build_dir/link.map"; then exit 1; fi
  fi
  sha256sum -c "$build_dir/inputs.sha256"
  ldd -r "$build_dir/$executable" > "$build_dir/runtime.log" 2>&1
  if rg 'not found|undefined symbol' "$build_dir/runtime.log"; then exit 1; fi
  mapfile -t runtime_files < <(awk '$2=="=>" && $3 ~ /^\// {print $3} $1 ~ /^\// {print $1}' \
                             "$build_dir/runtime.log" | sort -u)
  [[ ${#runtime_files[@]} -gt 0 ]]
  sha256sum "${runtime_files[@]}" > "$build_dir/runtime.sha256"
  executable_sha256=$(sha256sum "$build_dir/$executable" | awk '{print $1}')
  printf '%s  %s\n' "$executable_sha256" "$build_dir/$executable" > "$build_dir/executable.sha256"
  verified_runner="$repo_root/tools/run_bound_executable.py"
  verified_launcher="$build_dir/run_verified.sh"
  {
    printf '#!/usr/bin/env bash\nset -euo pipefail\n'
    printf 'sha256sum -c %q\n' "$build_dir/inputs.sha256"
    printf 'sha256sum -c %q\n' "$build_dir/runtime.sha256"
    printf 'exec %q %q --sha256-file %q %q -- "$@"\n' \
      python3 "$verified_runner" "$build_dir/executable.sha256" "$build_dir/$executable"
  } > "$verified_launcher"
  chmod 700 "$verified_launcher"
  printf 'BOUND_EXECUTABLE_SHA256 %s\n' "$executable_sha256"
  printf 'BOUND_LAUNCHER %s\n' "$verified_launcher"
  printf 'BUILD_AND_LINK_PASS; NOT_EXECUTED; NOT_GENERATION_READY\n'
} > "$build_dir/build.log" 2>&1
