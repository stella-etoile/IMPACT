#!/bin/sh

#SBATCH --job-name=TCR_##-gamd-equil
#SBATCH --exclusive
#SBATCH --time=32:00:00
#SBATCH --partition=caslake
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian


ulimit -l unlimited


module load namd


mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-gamd-equil.conf" > "TCR_##-gamd-equil.log"
