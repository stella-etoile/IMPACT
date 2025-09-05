#!/bin/sh

#SBATCH --job-name=TCR_##_npt1
#SBATCH --time=22:00:00
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=48
#SBATCH --output=TCR_##-npt1.out
#SBATCH --error=TCR_##-npt1.err

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-npt1.conf" &> "TCR_##-npt1.log"
