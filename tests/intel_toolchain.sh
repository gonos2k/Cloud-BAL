#!/usr/bin/env bash
# One authoritative Intel Fortran profile for Cloud-BAL tests and evidence.

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  printf '%s\n' 'intel_toolchain.sh must be sourced' >&2
  exit 2
fi

cloud_bal_setvars=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/setvars.sh
cloud_bal_expected_setvars_sha256=26084d08db985eadb61adc43c7f18821be9e75156b60f920de363ea51c70887e
if [[ ! -f $cloud_bal_setvars ]]; then
  printf 'Intel oneAPI environment script is required: %s\n' \
    "$cloud_bal_setvars" >&2
  return 2
fi
if [[ $(sha256sum "$cloud_bal_setvars" | cut -d' ' -f1) != \
      "$cloud_bal_expected_setvars_sha256" ]]; then
  printf 'unpinned Intel environment rejected: %s\n' "$cloud_bal_setvars" >&2
  return 2
fi
# setvars owns the compiler runtime search path needed by every generated
# executable.  It is not nounset-clean, so contain that legacy behavior here.
# Silence its banner so test output remains machine-readable.
set +u
if ! . "$cloud_bal_setvars" --force >/dev/null 2>&1; then
  set -u
  printf 'failed to initialize Intel oneAPI environment: %s\n' \
    "$cloud_bal_setvars" >&2
  return 2
fi
set -u

cloud_bal_default_ifx=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/bin/ifx
CLOUD_BAL_FC=${CLOUD_BAL_IFX:-$cloud_bal_default_ifx}
cloud_bal_expected_ifx_version='ifx (IFX) 2026.0.0 20260331'
cloud_bal_expected_ifx_sha256=909ac6dba06fb5af2e79760421718fb9f6a219f22ea4fa3bfdd9848385c5eaef
cloud_bal_imf=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libimf.so
cloud_bal_intlc=/NHNHOME/WORKSPACE/26weather002_A/yhlee/local/compiler/2026.0/lib/libintlc.so.5
cloud_bal_expected_imf_sha256=31f0ab1dcce74417de63e5c6876b5bb078c15efea4c49ca9afc233abbe80fda8
cloud_bal_expected_intlc_sha256=2722b7aba08edf1d37c45b8f90070c87b499404b0888bd1b4150f34e123ef120

if [[ ! -x $CLOUD_BAL_FC ]]; then
  printf 'Intel ifx is required and was not found: %s\n' "$CLOUD_BAL_FC" >&2
  return 2
fi

CLOUD_BAL_FC=$(readlink -f "$CLOUD_BAL_FC")
cloud_bal_fc_version=$($CLOUD_BAL_FC --version 2>&1 | sed -n '1p')
cloud_bal_fc_sha256=$(sha256sum "$CLOUD_BAL_FC" | cut -d' ' -f1)
if [[ $(basename "$CLOUD_BAL_FC") != ifx || \
      $cloud_bal_fc_version != "$cloud_bal_expected_ifx_version" || \
      $cloud_bal_fc_sha256 != "$cloud_bal_expected_ifx_sha256" ]]; then
  printf 'unpinned Intel compiler rejected: %s (%s)\n' \
    "$CLOUD_BAL_FC" "$cloud_bal_fc_version" >&2
  return 2
fi
if [[ $(sha256sum "$cloud_bal_imf" | cut -d' ' -f1) != \
      "$cloud_bal_expected_imf_sha256" || \
      $(sha256sum "$cloud_bal_intlc" | cut -d' ' -f1) != \
      "$cloud_bal_expected_intlc_sha256" ]]; then
  printf 'unpinned Intel runtime rejected\n' >&2
  return 2
fi

# Audit builds favor runtime diagnostics.  Reproduction builds use the same
# floating-point contract but may choose O2 explicitly after the audit passes.
CLOUD_BAL_FREE_FLAGS=(
  -stand f08
  -warn all
  -check all
  -fpe0
  -traceback
  -O0
  -fp-model strict
  -fimf-arch-consistency=true
  -no-ftz
)
CLOUD_BAL_REPRO_FLAGS=(
  -stand f08
  -warn all
  -fpe0
  -traceback
  -O2
  -fp-model strict
  -fimf-arch-consistency=true
  -no-ftz
)
CLOUD_BAL_FIXED_FLAGS=(
  -fixed
  -extend-source
  -check all
  -fpe0
  -traceback
  -O0
  -fp-model strict
  -fimf-arch-consistency=true
  -no-ftz
)
CLOUD_BAL_FIXED_72_FLAGS=(
  -fixed
  -extend-source 72
  -check all
  -fpe0
  -traceback
  -O0
  -fp-model strict
  -fimf-arch-consistency=true
  -no-ftz
)

export CLOUD_BAL_FC
