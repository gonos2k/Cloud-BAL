#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
test_root=$(mktemp -d)
trap 'rm -rf -- "$test_root"' EXIT
publication_root=$test_root/publication
transaction_id=shell-recovery-fixture

damaged_repo=$test_root/damaged-index-repo
mkdir -p "$damaged_repo"
git -C "$damaged_repo" init -q
git -C "$damaged_repo" -c user.name=fixture -c user.email=fixture@example.invalid \
  commit --allow-empty -qm fixture
printf 'damaged index\n' > "$damaged_repo/.git/index"
git -C "$damaged_repo" rev-parse HEAD >/dev/null
for call_mode in direct command_substitution; do
  if bash -c '
    set -euo pipefail
    repo_root=$1
    . "$repo_root/tests/output_safety.sh"
    repo_root=$2
    if [[ $3 == direct ]]; then
      cloud_bal_require_clean_source
    else
      status=$(cloud_bal_require_clean_source)
    fi
    exit 91
  ' _ "$repo_root" "$damaged_repo" "$call_mode" >/dev/null 2>&1; then
    printf 'damaged Git index was accepted: %s\n' "$call_mode" >&2
    exit 1
  else
    status=$?
    [[ $status -ne 0 && $status -ne 91 ]] || {
      printf 'damaged Git index failure was not propagated: %s (%d)\n' \
        "$call_mode" "$status" >&2
      exit 1
    }
  fi
done

python3 - "$test_root" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
head = "a" * 40
for case, generation_head, summary in (
    ("invalid_head", "b" * 40, {}),
    ("invalid_summary", head, "not-json"),
):
    generation = root / case
    generation.mkdir()
    (generation / "MANIFEST.json").write_text(
        json.dumps({"source_commit": generation_head}), encoding="utf-8"
    )
    summary_path = generation / "RUN_SUMMARY.json"
    summary_path.write_text(
        summary if isinstance(summary, str) else json.dumps(summary),
        encoding="utf-8",
    )
(root / "head").write_text(head, encoding="ascii")
PY

for evidence_case in invalid_head invalid_summary invalid_generation; do
  for call_mode in direct command_substitution; do
    if bash -c '
      set -euo pipefail
      repo_root=$1
      fixture_root=$2
      evidence_case=$3
      call_mode=$4
      . "$repo_root/tests/output_safety.sh"
      cloud_bal_require_clean_source() { return 0; }
      git() { cat "$fixture_root/head"; }
      python3() {
        if [[ $1 == "$repo_root/tools/cloud_bal_transaction.py" ]]; then
          case $evidence_case in
            invalid_head) printf "%s\n" "$fixture_root/invalid_head" ;;
            invalid_summary) printf "%s\n" "$fixture_root/invalid_summary" ;;
            invalid_generation) printf "%s\n" "$fixture_root/missing_generation" ;;
          esac
        else
          command python3 "$@"
        fi
      }
      if [[ $call_mode == direct ]]; then
        if cloud_bal_current_evidence /unused/publication \
          "$repo_root/tests/qbal_real_cases_20260816.tsv" >/dev/null; then
          exit 91
        else
          status=$?
          [[ $status -eq 1 ]] || exit 92
        fi
      else
        if evidence=$(cloud_bal_current_evidence /unused/publication \
          "$repo_root/tests/qbal_real_cases_20260816.tsv"); then
          exit 91
        else
          status=$?
          [[ $status -eq 1 ]] || exit 92
        fi
      fi
    ' _ "$repo_root" "$test_root" "$evidence_case" "$call_mode" \
      >/dev/null 2>&1; then
      :
    else
      printf 'evidence failure was not propagated: %s / %s\n' \
        "$evidence_case" "$call_mode" >&2
      exit 1
    fi
  done
done

staging=$(python3 "$repo_root/tools/cloud_bal_transaction.py" begin \
  "$publication_root" "$transaction_id" product.bin \
  --source-commit "$(git -C "$repo_root" rev-parse HEAD)" \
  --configuration shell-recovery-fixture --valid-time 1)
printf 'fixture product\n' > "$staging/product.bin"

set +e
bash -c '
  set -euo pipefail
  repo_root=$1
  staging=$2
  publication_root=$3
  transaction_id=$4
  . "$repo_root/tests/output_safety.sh"
  trap '\''cloud_bal_quarantine_staging_on_exit "$?" "$staging" \
    "$publication_root" "$transaction_id"'\'' EXIT
  CLOUD_BAL_FAIL_AT=after_generation_rename \
    python3 "$repo_root/tools/cloud_bal_transaction.py" commit \
      "$publication_root" "$transaction_id"
' _ "$repo_root" "$staging" "$publication_root" "$transaction_id"
commit_status=$?
set -e

[[ $commit_status -eq 2 ]]
[[ -d $staging ]]
[[ -d $publication_root/generations/$transaction_id ]]
[[ -f $publication_root/.owners/$transaction_id.json ]]
python3 "$repo_root/tools/cloud_bal_transaction.py" recover \
  "$publication_root" "$transaction_id" >/dev/null
current=$(python3 "$repo_root/tools/cloud_bal_transaction.py" current \
  "$publication_root")
[[ ${current##*/} == "$transaction_id" ]]

uncertain_id=shell-fsync-uncertain-fixture
uncertain_staging=$(python3 "$repo_root/tools/cloud_bal_transaction.py" begin \
  "$publication_root" "$uncertain_id" product.bin \
  --source-commit "$(git -C "$repo_root" rev-parse HEAD)" \
  --configuration shell-recovery-fixture --valid-time 2)
printf 'uncertain fixture product\n' > "$uncertain_staging/product.bin"
cat > "$test_root/fail_after_current_swap.py" <<'PY'
import errno
import os
import sys
import cloud_bal_transaction as transaction

root, transaction_id = sys.argv[1:]
real_fsync = os.fsync
injected = False

def fail_after_swap(descriptor):
    global injected
    target = os.fstat(descriptor)
    expected = os.stat(root)
    is_root = (target.st_dev, target.st_ino) == (expected.st_dev, expected.st_ino)
    if not injected and is_root and os.readlink(os.path.join(root, "current")) == \
            f"generations/{transaction_id}":
        injected = True
        raise OSError(errno.EIO, "injected post-current fsync failure")
    real_fsync(descriptor)

transaction.os.fsync = fail_after_swap
raise SystemExit(transaction.main(["commit", root, transaction_id]))
PY
set +e
bash -c '
  set -euo pipefail
  repo_root=$1
  wrapper=$2
  staging=$3
  publication_root=$4
  transaction_id=$5
  . "$repo_root/tests/output_safety.sh"
  trap '\''cloud_bal_quarantine_staging_on_exit "$?" "$staging" \
    "$publication_root" "$transaction_id"'\'' EXIT
  PYTHONPATH="$repo_root/tools" python3 "$wrapper" \
    "$publication_root" "$transaction_id"
' _ "$repo_root" "$test_root/fail_after_current_swap.py" \
  "$uncertain_staging" "$publication_root" "$uncertain_id"
uncertain_status=$?
set -e
[[ $uncertain_status -eq 3 ]]
[[ -d $uncertain_staging ]]
[[ -d $publication_root/generations/$uncertain_id ]]
[[ -f $publication_root/.owners/$uncertain_id.json ]]
python3 "$repo_root/tools/cloud_bal_transaction.py" recover \
  "$publication_root" "$uncertain_id" >/dev/null
current=$(python3 "$repo_root/tools/cloud_bal_transaction.py" current \
  "$publication_root")
[[ ${current##*/} == "$uncertain_id" ]]

prepublication_id=shell-prepublication-fixture
prepublication_staging=$(python3 "$repo_root/tools/cloud_bal_transaction.py" begin \
  "$publication_root" "$prepublication_id" product.bin \
  --source-commit "$(git -C "$repo_root" rev-parse HEAD)" \
  --configuration shell-recovery-fixture --valid-time 2)
set +e
bash -c '
  set -euo pipefail
  repo_root=$1
  staging=$2
  publication_root=$3
  transaction_id=$4
  . "$repo_root/tests/output_safety.sh"
  trap '\''cloud_bal_quarantine_staging_on_exit "$?" "$staging" \
    "$publication_root" "$transaction_id"'\'' EXIT
  exit 7
' _ "$repo_root" "$prepublication_staging" "$publication_root" \
  "$prepublication_id"
prepublication_status=$?
set -e
[[ $prepublication_status -eq 7 ]]
[[ ! -e $prepublication_staging ]]
compgen -G "$prepublication_staging.failed.*" >/dev/null

printf 'Evidence failures propagated in both call forms; same-ID post-current fsync recovery and prepublication quarantine passed\n'
