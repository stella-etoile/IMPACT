#!/bin/sh

#SBATCH --job-name=TCR_##_mini
#SBATCH --time=00:04:00
#SBATCH --partition=caslake
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=NONE
#SBATCH --output=TCR_##-mini.out
#SBATCH --error=TCR_##-mini.err

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-mini.conf" > "TCR_##-mini.log"

