#!/bin/bash
set -euo pipefail
source /var/tmp/firsthour-runtime-plan-20261030/producer_pair/export/tests/intel_toolchain.sh
ulimit -s unlimited
exec python3 /var/tmp/firsthour-runtime-plan-20261030/producer_pair/run_producer.py "$@"
