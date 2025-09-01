#!/bin/sh

#SBATCH --job-name=TCR_##_npt2
#SBATCH --time=4:00:00
#SBATCH --partition=caslake
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=48
#SBATCH --account=workshop-aiml
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=END,FAIL
#SBATCH --output=TCR_##-npt1.out
#SBATCH --error=TCR_##-npt1.err

ulimit -l unlimited

module load namd

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-npt2.conf" > "TCR_##-npt2.log"
