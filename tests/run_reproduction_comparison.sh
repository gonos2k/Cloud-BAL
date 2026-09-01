#!/usr/bin/env bash
set -euo pipefail

export LC_ALL=C

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
. "$repo_root/tests/intel_toolchain.sh"
baseline="$repo_root/scratch/baseline_legacy_0d4c9a8_20260816"
candidate_parent=$(realpath -m "$repo_root/scratch/candidate")
case_manifest_relative=tests/reproduction_cases_20260816.tsv
expected_case_manifest_sha256=addcbd4dda4743f5c96731126dc309c64dc26c7f5ae66e7c0d4e48c935619ff3
if [[ $# -gt 0 && $1 != --* ]]; then
  output=$1
  shift
elif [[ -n ${CLOUD_BAL_CANDIDATE_ROOT:-} ]]; then
  output=$CLOUD_BAL_CANDIDATE_ROOT
else
  mkdir -p "$candidate_parent"
  output=$(mktemp -d "$candidate_parent/reproduction.XXXXXX")
fi

if [[ $# -gt 0 ]]; then
  printf 'unknown option: %s\n' "$1" >&2
  exit 2
fi

output=$(realpath -m "$output")
if [[ $(dirname "$output") != "$candidate_parent" ]]; then
  printf 'output must be a direct child of %s\n' "$candidate_parent" >&2
  exit 2
fi
if [[ -L "$output" ]]; then
  printf 'output must not be a symbolic link: %s\n' "$output" >&2
  exit 2
fi
if [[ -d "$output" ]]; then
  if find "$output" -mindepth 1 -print -quit | grep -q .; then
    printf 'output must be empty: %s\n' "$output" >&2
    exit 2
  fi
else
  mkdir "$output"
fi
mkdir "$output/build"

if [[ -n $(git -C "$repo_root" status --porcelain --untracked-files=normal) ]]; then
  printf 'trusted reproduction requires a clean source tree\n' >&2
  exit 2
fi

source_commit=$(git -C "$repo_root" rev-parse HEAD)
source_tree=$(git -C "$repo_root" rev-parse 'HEAD^{tree}')
compiler_version=$("$CLOUD_BAL_FC" --version | sed -n '1p')
compiler_path=$CLOUD_BAL_FC
compiler_sha256=$(sha256sum "$compiler_path" | awk '{print $1}')
compiler_target=$("$CLOUD_BAL_FC" -dumpmachine)
host_kernel=$(uname -srm)
compiler_flags=$(printf '%q ' "${CLOUD_BAL_FREE_FLAGS[@]}")
snapshot_root="$output/source"
mkdir "$snapshot_root"
git -C "$repo_root" archive --format=tar HEAD | tar -xf - -C "$snapshot_root"
case_manifest="$snapshot_root/$case_manifest_relative"
case_manifest_sha256=$(sha256sum "$case_manifest" | awk '{print $1}')
if [[ $case_manifest_sha256 != "$expected_case_manifest_sha256" ]]; then
  printf 'case manifest is not the pinned 3x3 comparison set\n' >&2
  exit 2
fi

{
  printf 'source_commit=%s\n' "$source_commit"
  printf 'source_tree=%s\n' "$source_tree"
  printf 'worktree_porcelain_clean=1\n'
  printf 'compiled_source=git_archive_head\n'
  printf 'compiler=%s\n' "$compiler_version"
  printf 'compiler_path=%s\n' "$compiler_path"
  printf 'compiler_sha256=%s\n' "$compiler_sha256"
  printf 'compiler_target=%s\n' "$compiler_target"
  printf 'host_kernel=%s\n' "$host_kernel"
  printf 'compiler_flags=%s\n' "$compiler_flags"
} > "$output/provenance.txt"

sha256sum \
  "$snapshot_root/src/common/cloud_bal_state.f90" \
  "$snapshot_root/src/common/cloud_bal_column_physics.f90" \
  "$snapshot_root/src/common/cloud_bal_balance_operator.f90" \
  "$snapshot_root/src/common/cloud_bal_pipeline.f90" \
  "$snapshot_root/tests/intel_toolchain.sh" \
  "$snapshot_root/tests/reproduction_probe.f90" \
  > "$output/compiled_sources.sha256"

(cd "$baseline" && \
  sha256sum -c "$snapshot_root/tests/baseline_legacy_0d4c9a8.sha256" && \
  sha256sum -c SHA256SUMS) > "$output/baseline_integrity.txt"

python3 "$snapshot_root/tools/compare_baseline.py" \
  "$baseline/ANAL/NE57/DASV" \
  "$workspace_root/ANAL/NE57/DASV" > "$output/laps_snapshot_identity.txt"

product_report="$output/declared_product_identity.tsv"
printf 'group\tvalid_time\tsha256\tresult\n' > "$product_report"

while IFS=$'\t' read -r group valid_time relative; do
  if [[ $group == group ]]; then
    continue
  fi
  archived="$baseline/$relative"
  live="$workspace_root/$relative"
  if [[ -L "$archived" || -L "$live" || ! -f "$archived" || ! -f "$live" ]]; then
    printf 'declared products must be independent regular files: %s\n' "$relative" >&2
    exit 2
  fi
  if [[ $(stat -c '%h' "$archived") -ne 1 || $(stat -c '%h' "$live") -ne 1 || \
        $(stat -c '%d:%i' "$archived") == $(stat -c '%d:%i' "$live") ]]; then
    printf 'declared products must not be hard-linked: %s\n' "$relative" >&2
    exit 2
  fi
  cmp "$archived" "$live"
  digest=$(sha256sum "$archived" | awk '{print $1}')
  printf '%s\t%s\t%s\tIDENTICAL\n' "$group" "$valid_time" "$digest" \
    >> "$product_report"
done < "$case_manifest"

dependency_report="$output/legacy_runtime_dependencies.txt"
: > "$dependency_report"
for executable in klps_anal_derv.exe klps_anal_qbal.exe klps_anal_prep.exe; do
  printf 'executable=%s\n' "$executable" >> "$dependency_report"
  ldd "$baseline/klaps-v5.0_/bin/$executable" >> "$dependency_report"
done

missing_library_links=$(awk '/not found/{count++} END{print count+0}' \
  "$dependency_report")
runtime_intermediate_count=$(find "$baseline/ANAL" -type f \
  \( -name lco -o -name lcp -o -name lw3 -o -name lwc -o -path '*/balance/*' \) \
  | wc -l)
environment_script=${CLOUD_BAL_LEGACY_ENV_SCRIPT:-/home/korea_keun/jobs/NE57/UTIL/ENVI/kl05_src}
environment_script_present=0
if [[ -f "$environment_script" ]]; then
  environment_script_present=1
fi

"$snapshot_root/tests/run_unit_tests.sh" > "$output/focused_unit_suite.txt" 2>&1

(
  cd "$output/build"
  "$CLOUD_BAL_FC" "${CLOUD_BAL_FREE_FLAGS[@]}" \
    -module "$output/build" -I "$output/build" \
    "$snapshot_root/src/common/cloud_bal_state.f90" \
    "$snapshot_root/src/common/cloud_bal_column_physics.f90" \
    "$snapshot_root/src/common/cloud_bal_balance_operator.f90" \
    "$snapshot_root/src/common/cloud_bal_pipeline.f90" \
    "$snapshot_root/tests/reproduction_probe.f90" \
    -o "$output/build/cloud_bal_reproduction_probe"
)

for repeat in 1 2 3; do
  "$output/build/cloud_bal_reproduction_probe" \
    > "$output/canonical_probe_${repeat}.txt"
done

cmp "$output/canonical_probe_1.txt" "$output/canonical_probe_2.txt"
cmp "$output/canonical_probe_1.txt" "$output/canonical_probe_3.txt"
sha256sum "$output"/canonical_probe_?.txt > "$output/canonical_probe_sha256.txt"
probe_sha=$(sha256sum "$output/canonical_probe_1.txt" | awk '{print $1}')
probe_binary_sha=$(sha256sum "$output/build/cloud_bal_reproduction_probe" | awk '{print $1}')

laps_count=$(awk -F '\t' '$1=="LAPS" && $4=="IDENTICAL"{count++} END{print count+0}' \
  "$product_report")
klbg_count=$(awk -F '\t' '$1=="KLBG" && $4=="IDENTICAL"{count++} END{print count+0}' \
  "$product_report")
met_em_count=$(awk -F '\t' '$1=="MET_EM" && $4=="IDENTICAL"{count++} END{print count+0}' \
  "$product_report")
total_count=$(awk -F '\t' '$4=="IDENTICAL"{count++} END{print count+0}' \
  "$product_report")
if [[ $laps_count -ne 3 || $klbg_count -ne 3 || $met_em_count -ne 3 || \
      $total_count -ne 9 ]]; then
  printf 'declared snapshot comparison did not produce the pinned 3/3/3/9 set\n' >&2
  exit 2
fi

legacy_rerun_status=BLOCKED
if [[ $missing_library_links -eq 0 && $runtime_intermediate_count -gt 0 && \
      $environment_script_present -eq 1 ]]; then
  legacy_rerun_status=NOT_RUN
fi

summary="$output/summary.txt"
{
  printf 'experiment=cloud_bal_reproduction_comparison_v2\n'
  printf 'source_commit=%s\n' "$source_commit"
  printf 'source_tree=%s\n' "$source_tree"
  printf 'worktree_porcelain_clean=1\n'
  printf 'compiled_source=git_archive_head\n'
  printf 'legacy_source_commit_claim=0d4c9a8e7a9c518867df80141b80f2f35d73250e\n'
  printf 'legacy_binary_source_binding=UNVERIFIED\n'
  printf 'legacy_snapshot_integrity=PASS\n'
  printf 'snapshot_identity_scope=declared_20260816_13_14_15_utc_products\n'
  printf 'snapshot_manifest_sha256=%s\n' "$case_manifest_sha256"
  printf 'snapshot_laps_identical_pairs=%s\n' "$laps_count"
  printf 'snapshot_klbg_identical_pairs=%s\n' "$klbg_count"
  printf 'snapshot_met_em_identical_pairs=%s\n' "$met_em_count"
  printf 'snapshot_total_identical_pairs=%s\n' "$total_count"
  printf 'legacy_missing_runtime_library_links=%s\n' "$missing_library_links"
  printf 'legacy_runtime_intermediate_files=%s\n' "$runtime_intermediate_count"
  printf 'legacy_environment_script_present=%s\n' "$environment_script_present"
  printf 'legacy_executable_rerun=%s\n' "$legacy_rerun_status"
  printf 'real_case_algorithm_comparison=NOT_RUN\n'
  printf 'focused_unit_suite=PASS\n'
  printf 'canonical_synthetic_probe=PASS\n'
  printf 'canonical_probe_repeats=3\n'
  printf 'canonical_probe_repeat_identity=PASS\n'
  printf 'canonical_probe_binary_sha256=%s\n' "$probe_binary_sha"
  printf 'canonical_probe_sha256=%s\n' "$probe_sha"
  printf 'overall_evidence=PARTIAL\n'
  printf 'promotion_eligible=0\n'
} > "$summary"

printf 'diagnostic_complete=1\npromotion_eligible=0\n' \
  > "$output/DIAGNOSTIC_COMPLETE"
printf 'Diagnostic reproduction evidence completed with legacy rerun %s: %s\n' \
  "$legacy_rerun_status" "$output"
sed -n '1,160p' "$summary"
sed -n '1,180p' "$output/canonical_probe_1.txt"

if [[ $legacy_rerun_status != COMPLETED ]]; then
  printf 'full real-case reproduction is incomplete; diagnostic evidence cannot satisfy this gate\n' >&2
  exit 3
fi
