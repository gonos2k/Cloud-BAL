#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workspace_root=$(cd "$repo_root/.." && pwd)
baseline="$repo_root/scratch/baseline_legacy_0d4c9a8_20260816"
candidate_parent="$repo_root/scratch/candidate"

if [[ $# -lt 1 ]]; then
  printf 'usage: %s CANDIDATE_ROOT [-- command ...]\n' "$0" >&2
  exit 2
fi

candidate=$(realpath -m "$1")
shift
if [[ ${1-} == -- ]]; then shift; fi
candidate_parent_real=$(realpath -m "$candidate_parent")
case "$candidate/" in
  "$candidate_parent_real"/*) ;;
  *) printf 'candidate must be below %s\n' "$candidate_parent_real" >&2; exit 2 ;;
esac

for protected in "$workspace_root/ANAL" "$workspace_root/MODL" "$baseline"; do
  protected=$(realpath "$protected")
  case "$candidate/" in
    "$protected"/*) printf 'candidate resolves inside protected root: %s\n' "$protected" >&2; exit 2 ;;
  esac
done

if find "$baseline/ANAL" "$baseline/MODL" "$baseline/klaps-v5.0_" -type l -print -quit | grep -q .; then
  printf 'baseline contains a symbolic link\n' >&2
  exit 1
fi
if find "$baseline/ANAL" "$baseline/MODL" "$baseline/klaps-v5.0_" -type f -links +1 -print -quit | grep -q .; then
  printf 'baseline contains a multiply-linked file\n' >&2
  exit 1
fi
if find "$baseline/ANAL" "$baseline/MODL" "$baseline/klaps-v5.0_" -type f -perm /0222 -print -quit | grep -q .; then
  printf 'baseline contains a writable payload\n' >&2
  exit 1
fi

(cd "$baseline" && sha256sum -c SHA256SUMS)
mkdir -p "$candidate" "$repo_root/scratch"
gate_tmp=$(mktemp -d "$repo_root/scratch/isolation_gate.XXXXXX")
trap 'rm -rf "$gate_tmp"' EXIT

hash_live_inputs() {
  local destination=$1 digest relative live
  : > "$destination"
  while read -r digest relative; do
    case "$relative" in
      ANAL/*|MODL/*)
        live="$workspace_root/$relative"
        if [[ ! -f "$live" ]]; then
          printf 'declared live input is missing: %s\n' "$live" >&2
          return 1
        fi
        sha256sum "$live" >> "$destination"
        ;;
    esac
  done < "$baseline/SHA256SUMS"
}

hash_live_inputs "$gate_tmp/before.sha256"
if [[ $# -gt 0 ]]; then
  CLOUD_BAL_CANDIDATE_ROOT="$candidate" "$@"
fi
hash_live_inputs "$gate_tmp/after.sha256"
cmp "$gate_tmp/before.sha256" "$gate_tmp/after.sha256"
(cd "$baseline" && sha256sum -c SHA256SUMS)

printf 'Cloud-BAL isolation gate passed: %s\n' "$candidate"
