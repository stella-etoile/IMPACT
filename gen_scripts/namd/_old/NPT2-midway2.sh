#!/bin/sh

#SBATCH --job-name=TCR_##_npt2
#SBATCH --time=12:00:00
#SBATCH --partition=gpu2
#SBATCH --nodes=4
#SBATCH --ntasks-per-node=28
#SBATCH --account=pi-haddadian
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=END,FAIL
#SBATCH --output=TCR_##-npt1.out
#SBATCH --error=TCR_##-npt1.err

ulimit -l unlimited

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-npt2.conf" > "TCR_##-npt2.log"
