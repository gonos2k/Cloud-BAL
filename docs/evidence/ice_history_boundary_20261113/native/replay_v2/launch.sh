#!/usr/bin/env bash
set -eo pipefail
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/tests/intel_toolchain.sh
export NETCDF=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel
export LD_LIBRARY_PATH="$NETCDF/lib:$LD_LIBRARY_PATH"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export I_MPI_PIN=1 I_MPI_PIN_DOMAIN=core I_MPI_PIN_RESPECT_CPUSET=1 I_MPI_PIN_PROCESSOR_LIST=24,25,26,27,28,29,30,31
export GROUPED_CPUS=24,25,26,27,28,29,30,31
ulimit -s unlimited
cd /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/ice_history_boundary_20261113/native/replay_v2/run
ldd ./wrf.exe > ../ldd.txt
date -u +%FT%TZ > ../start.utc
set +e
taskset -c "$GROUPED_CPUS" /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun -np 8 /bin/bash ../rank_wrapper.sh > ../launcher.log 2>&1
status=$?
set -e
printf '%s\n' "$status" > ../exit.status
date -u +%FT%TZ > ../end.utc
exit "$status"
