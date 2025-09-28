#!/bin/sh

#SBATCH --job-name=TCR_##_equil
#SBATCH --time=03:15:00
#SBATCH --partition=caslake
#SBATCH --nodes=4
#SBATCH --mem=16G
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=END,FAIL
#SBATCH --output=TCR_##-equil.out
#SBATCH --error=TCR_##-equil.err

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-heatup-equil.conf" &> "TCR_##-heatup-equil.log"
