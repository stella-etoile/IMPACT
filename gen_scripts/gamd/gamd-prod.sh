#!/bin/sh

#SBATCH --job-name=TCR_##-gamd-npt1
#SBATCH --time=18:00:00
#SBATCH --partition=caslake
#SBATCH --nodes=6
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian
#SBATCH --mail-type=END,FAIL
#SBATCH --mail-user=kangheelee@rcc.chicago.edu
#SBATCH --output=TCR_##-npt1.out
#SBATCH --error=TCR_##-npt1.err

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-gamd-npt1.conf" > "TCR_##-gamd-npt1.log"
