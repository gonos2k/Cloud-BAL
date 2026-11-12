#!/usr/bin/env bash
set -eo pipefail
root=$(cd "$(dirname "$0")/../../../.." && pwd)
runtime=${1:-"$root/../native_runtime"}
mkdir -p "$runtime/tmp"
runtime=$(cd "$runtime" && pwd)
source "$root/tests/intel_toolchain.sh"
set +u
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/env/vars.sh >/dev/null 2>&1
set -u
export LD_LIBRARY_PATH="/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel/lib:$LD_LIBRARY_PATH"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE I_MPI_PIN=1 I_MPI_PIN_DOMAIN=core I_MPI_PIN_RESPECT_CPUSET=1 I_MPI_PIN_PROCESSOR_LIST=48,49,50,51,52,53,54,55 TMPDIR="$runtime/tmp"
export ICE_SCRIPT="$root/docs/evidence/first_call_water_budget_20261112/native/probe.py" ICE_WRAPPER="$root/docs/evidence/first_call_water_budget_20261112/native/rank_wrapper.sh"
ulimit -s unlimited
for arm in control_terminal probe_terminal; do
 d="$runtime/$arm"; cd "$d"
 TIMEFORMAT='%R'
 if [[ $arm = control_terminal ]]; then
  { time timeout 300 taskset -c 48-55 /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun -np 8 ./wrf.exe >stdout.txt 2>&1; } 2>elapsed.txt
 else
  export ICE_OUT="$d/capture"; mkdir "$ICE_OUT"
  { time timeout 300 taskset -c 48-55 /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun -np 8 /bin/bash "$ICE_WRAPPER" >stdout.txt 2>&1; } 2>elapsed.txt
 fi
done
