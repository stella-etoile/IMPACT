#!/bin/sh

#SBATCH --job-name=TCR_##_npt1
#SBATCH --time=20:10:00
#SBATCH --qos=caslake-prio
#SBATCH --partition=caslake
#SBATCH --nodes=4
#SBATCH --mem=16G
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=END,FAIL
#SBATCH --output=TCR_##-npt2.out
#SBATCH --error=TCR_##-npt2.err

module load namd/2.14

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-npt1.conf" &> "TCR_##-npt1.log"
