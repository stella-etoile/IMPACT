#!/bin/sh

#SBATCH --job-name=TCR_##_equil
#SBATCH --time=03:30:00
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=48
#SBATCH --output=TCR_##-equil.out
#SBATCH --error=TCR_##-equil.err

module load namd

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-heatup-equil.conf" &> "TCR_##-heatup-equil.log"
