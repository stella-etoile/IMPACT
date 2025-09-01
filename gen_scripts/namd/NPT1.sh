#!/bin/sh

#SBATCH --job-name=TCR_##_npt1
#SBATCH --time=22:00:00 # This needs to be extended to 40 hrs.
#SBATCH --partition=caslake
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=48
#SBATCH --account=workshop-aiml
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=END,FAIL
#SBATCH --output=TCR_##-npt2.out
#SBATCH --error=TCR_##-npt2.err

# I DO NOT RECOMMEND RUNNING THIS; THIS WILL GO OVER TIME

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-npt1.conf" &> "TCR_##-npt1.log"
