#!/bin/sh

#SBATCH --job-name=TCR_##-gamd-equil
#SBATCH --exclusive
#SBATCH --time=32:00:00
#SBATCH --partition=caslake
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian

ulimit -l unlimited

# module load namd
module load namd/3.0.1-multicore-cuda

# mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-gamd-equil.conf" > "TCR_##-gamd-equil.log"
$NAMD_HOME/namd3 +p 32 +devices 0,1,2,3 +setcpuaffinity 'TCR_##-gamd-equil.conf'  > 'TCR_##-gamd-equil.log'
