#!/bin/sh

#SBATCH --job-name=TCR_##_mini
#SBATCH --time=00:10:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=8
#SBATCH --output=TCR_##-mini.out
#SBATCH --error=TCR_##-mini.err

module load namd

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-mini.conf" > "TCR_##-mini.log"

