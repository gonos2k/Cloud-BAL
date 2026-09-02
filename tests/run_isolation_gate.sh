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

candidate_parent_lexical=$(realpath -ms "$candidate_parent")
if [[ ! -d "$candidate_parent_lexical" || -L "$candidate_parent_lexical" ]] || \
   [[ $(realpath -e "$candidate_parent_lexical") != "$candidate_parent_lexical" ]]; then
  printf 'candidate parent must be a real, non-symlink directory: %s\n' \
    "$candidate_parent_lexical" >&2
  exit 2
fi
candidate=$(realpath -m "$1")
shift
if [[ ${1-} == -- ]]; then shift; fi
candidate_parent_real=$(realpath -e "$candidate_parent_lexical")
case "$candidate/" in
  "$candidate_parent_real"/*) ;;
  *) printf 'candidate must be below %s\n' "$candidate_parent_real" >&2; exit 2 ;;
esac

for protected in "$workspace_root/ANAL" "$workspace_root/MODL" \
    "$workspace_root/klaps-v5.0_" "$baseline"; do
  protected=$(realpath "$protected")
  case "$candidate/" in
    "$protected"/*) printf 'candidate resolves inside protected root: %s\n' "$protected" >&2; exit 2 ;;
  esac
done

mkdir -p "$(dirname "$candidate")" "$repo_root/scratch"
if [[ -e "$candidate" || -L "$candidate" ]]; then
  if [[ -L "$candidate" || ! -d "$candidate" ]] || \
      find "$candidate" -mindepth 1 -print -quit | grep -q .; then
    printf 'candidate must be a new or empty directory: %s\n' "$candidate" >&2
    exit 2
  fi
else
  mkdir "$candidate"
fi
gate_tmp=$(mktemp -d "$repo_root/scratch/isolation_gate.XXXXXX")
trap 'rm -rf "$gate_tmp"' EXIT
git -C "$repo_root" show HEAD:tests/baseline_legacy_0d4c9a8.sha256 \
  > "$gate_tmp/baseline_anchor.sha256"

check_baseline_contract() {
  local expected="$gate_tmp/expected_files" actual="$gate_tmp/actual_files"
  if find "$baseline/ANAL" "$baseline/MODL" "$baseline/klaps-v5.0_" \
      -type l -print -quit | grep -q .; then
    printf 'baseline contains a symbolic link\n' >&2
    return 1
  fi
  if find "$baseline/ANAL" "$baseline/MODL" "$baseline/klaps-v5.0_" \
      -type f -links +1 -print -quit | grep -q .; then
    printf 'baseline contains a multiply-linked file\n' >&2
    return 1
  fi
  if find "$baseline/ANAL" "$baseline/MODL" "$baseline/klaps-v5.0_" \
      -type f -perm /0222 -print -quit | grep -q .; then
    printf 'baseline contains a writable payload\n' >&2
    return 1
  fi
  sed -E 's/^[[:xdigit:]]{64}  //' "$baseline/SHA256SUMS" | sort > "$expected"
  (cd "$baseline" && find ANAL MODL klaps-v5.0_ -type f -printf '%p\n' | sort) \
    > "$actual"
  cmp "$expected" "$actual"
  (cd "$baseline" && sha256sum -c "$gate_tmp/baseline_anchor.sha256")
  (cd "$baseline" && sha256sum -c SHA256SUMS)
}

inventory_baseline() {
  local destination=$1
  (cd "$baseline" && find . \
    -printf '%p\t%y\t%m\t%n\t%s\t%T@\t%C@\t%D:%i\t%l\n' | sort) \
    > "$destination"
}

inventory_live_tree() {
  local destination=$1
  (cd "$workspace_root" && find ANAL MODL klaps-v5.0_ -xdev \
    -printf '%p\t%y\t%m\t%n\t%s\t%T@\t%C@\t%l\n' | sort) > "$destination"
}

check_candidate_contract() {
  if find "$candidate" -type l -print -quit | grep -q .; then
    printf 'candidate evidence contains a symbolic link\n' >&2
    return 1
  fi
  if find "$candidate" -type f -links +1 -print -quit | grep -q .; then
    printf 'candidate evidence contains a multiply-linked file\n' >&2
    return 1
  fi
  if find "$candidate" -mindepth 1 ! -type d ! -type f -print -quit | grep -q .; then
    printf 'candidate evidence contains a non-regular entry\n' >&2
    return 1
  fi
}

hash_live_inputs() {
  local destination=$1 digest relative live lexical resolved actual
  : > "$destination"
  while read -r digest relative; do
    case "$relative" in
      ANAL/*|MODL/*|klaps-v5.0_/*)
        live="$workspace_root/$relative"
        lexical=$(realpath -ms "$live")
        resolved=$(realpath -e "$live" 2>/dev/null || true)
        if [[ ! -f "$live" || -L "$live" || -z "$resolved" || \
              "$lexical" != "$resolved" ]]; then
          printf 'declared live input is missing or symlinked: %s\n' "$live" >&2
          return 1
        fi
        if [[ $(stat -c '%h' "$live") -ne 1 ]]; then
          printf 'declared live input is multiply linked: %s\n' "$live" >&2
          return 1
        fi
        actual=$(sha256sum "$live" | awk '{print $1}')
        if [[ $actual != "$digest" ]]; then
          printf 'declared live input differs from immutable baseline: %s\n' \
            "$relative" >&2
          return 1
        fi
        printf '%s  %s\n' "$actual" "$relative" >> "$destination"
        ;;
    esac
  done < "$baseline/SHA256SUMS"
}

check_baseline_contract
inventory_baseline "$gate_tmp/baseline.before"
hash_live_inputs "$gate_tmp/before.sha256"
inventory_live_tree "$gate_tmp/before.inventory"
command_status=0
if [[ $# -gt 0 ]]; then
  CLOUD_BAL_CANDIDATE_ROOT="$candidate" "$@" || command_status=$?
fi
hash_live_inputs "$gate_tmp/after.sha256"
inventory_live_tree "$gate_tmp/after.inventory"
inventory_baseline "$gate_tmp/baseline.after"
cmp "$gate_tmp/before.sha256" "$gate_tmp/after.sha256"
cmp "$gate_tmp/before.inventory" "$gate_tmp/after.inventory"
cmp "$gate_tmp/baseline.before" "$gate_tmp/baseline.after"
check_baseline_contract
check_candidate_contract

if [[ $command_status -ne 0 ]]; then
  printf 'isolated command failed with status %s\n' "$command_status" >&2
  exit "$command_status"
fi

printf 'Cloud-BAL declared-input hashes and live-tree metadata remained unchanged: %s\n' \
  "$candidate"
