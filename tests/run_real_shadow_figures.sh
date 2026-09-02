#!/usr/bin/env bash
# Plot every prepared case with one deterministic rule; never select cases by outcome.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
. "$repo_root/tests/output_safety.sh"
manifest=$repo_root/tests/qbal_real_cases_20260816.tsv
cloud_bal_require_clean_source
[[ $# -le 1 ]] || { printf 'usage: %s [FIGURE_ROOT]\n' "$0" >&2; exit 2; }
diagnostic_root=$(cloud_bal_current_evidence \
  "$repo_root/scratch/publications/real_shadow" "$manifest")
figure_root=$(cloud_bal_output_under \
  "${1:-$repo_root/scratch/figures/real_shadow}" "$repo_root/scratch/figures")
case $figure_root in
  "$diagnostic_root"|"$diagnostic_root"/*)
    printf 'figure output cannot modify its diagnostic generation\n' >&2
    exit 2
    ;;
esac

mkdir -p "$figure_root"
expected_count=$(($(wc -l < "$manifest") - 1))
case_count=0
while IFS=$'\t' read -r case_id _; do
  [[ $case_id == case_id ]] && continue
  diagnostic=$diagnostic_root/$case_id.nc
  report=$diagnostic_root/$case_id.json
  [[ -f $diagnostic && -f $report ]] || {
    printf 'missing validated case %s\n' "$case_id" >&2
    exit 2
  }
  python3 "$repo_root/tools/validate_shadow_diagnostics.py" "$diagnostic" >/dev/null
  python3 "$repo_root/tools/plot_shadow_comparison.py" "$diagnostic" "$figure_root"
  case_count=$((case_count + 1))
done < "$manifest"

[[ $case_count -eq $expected_count && $case_count -gt 0 ]] || exit 2
[[ $(find "$figure_root" -maxdepth 1 -type f -name '*.png' | wc -l) -eq $((2 * case_count)) ]] || exit 2
generation_after=$(cloud_bal_current_evidence \
  "$repo_root/scratch/publications/real_shadow" "$manifest")
[[ $generation_after == "$diagnostic_root" ]] || {
  printf 'diagnostic generation changed while plotting\n' >&2
  exit 2
}
printf 'REAL SHADOW FIGURES PASS: %d/%d cases, deterministic selection\n' \
  "$case_count" "$case_count"
