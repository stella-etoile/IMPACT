#!/bin/sh

#SBATCH --job-name=TCR_##_npt2
#SBATCH --time=4:00:00
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=48
#SBATCH --output=TCR_##-npt2.out
#SBATCH --error=TCR_##-npt2.err

ulimit -l unlimited

module load namd

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-npt2.conf" > "TCR_##-npt2.log"
