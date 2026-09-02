#!/usr/bin/env bash
# Read-only production integration gate. BLOCKED is exit 3, not a test crash.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

if (( $# != 0 )); then
  if (( $# != 2 )) || [[ $1 != --output ]]; then
    printf '%s\n' 'usage: run_intel_integration_audit.sh [--output PATH]' >&2
    exit 2
  fi
fi

unset LD_PRELOAD LD_AUDIT LD_DEBUG LD_DEBUG_OUTPUT LD_PROFILE LD_PROFILE_OUTPUT
unset GCONV_PATH LOCPATH LD_LIBRARY_PATH LIBRARY_PATH CPATH
unset MAKEFLAGS MAKEFILES MFLAGS GNUMAKEFLAGS BASH_ENV ENV CDPATH
. "$repo_root/tests/intel_toolchain.sh"

exec /usr/bin/python3 "$repo_root/tools/audit_intel_integration.py" "$@"
