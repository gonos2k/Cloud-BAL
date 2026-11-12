#!/usr/bin/env bash
set -eo pipefail
source /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/Cloud-BAL/tests/intel_toolchain.sh
export NETCDF=/NHNHOME/WORKSPACE/26weather002_A/yhlee/KIM-meso/deps/netcdf-intel
export LD_LIBRARY_PATH="$NETCDF/lib:$LD_LIBRARY_PATH"
export OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE MKL_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
export I_MPI_PIN=1 I_MPI_PIN_DOMAIN=core I_MPI_PIN_RESPECT_CPUSET=1 I_MPI_PIN_PROCESSOR_LIST=24,25,26,27,28,29,30,31
export GROUPED_CPUS=24,25,26,27,28,29,30,31 GROUPED_PYTHON=/usr/bin/python3
ulimit -s unlimited
cd /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/actual_prior_first_use_20261112/prior_forecast/run
ldd ./wrf.exe > ../ldd.txt
sha256sum wrf.exe wrfinput_d01 wrfbdy_d01 namelist.input physical_history.txt > ../before.sha256
date -u +%FT%TZ > ../start.utc
set +e
taskset -c "$GROUPED_CPUS" /NHNHOME/WORKSPACE/26weather002_A/yhlee/local/mpi/2021.18/bin/mpirun -np 8 /bin/bash /NHNHOME/WORKSPACE/26weather002_A/yhlee/KLAPS50/scratch/b1_activation_path_20261110/Cloud-BAL/docs/evidence/cp02_activation_path_20261110/native/runs/rank_wrapper.sh > ../launcher.log 2>&1
status=$?
set -e
printf '%s\n' "$status" > ../exit.status
date -u +%FT%TZ > ../end.utc
sha256sum wrf.exe wrfinput_d01 wrfbdy_d01 namelist.input physical_history.txt > ../after.sha256
exit "$status"
