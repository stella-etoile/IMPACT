#!/bin/sh

#SBATCH --job-name=TCR_##_mini
#SBATCH --time=00:08:00
#SBATCH --partition=caslake
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=28
#SBATCH --account=pi-haddadian
#SBATCH --mail-user=kangheelee@rcc.uchicago.edu
#SBATCH --mail-type=NONE
#SBATCH --output=TCR_##-mini.out
#SBATCH --error=TCR_##-mini.err

BYPASS=false

for arg in "$@"; do
  if [[ "$arg" == "--bypass" ]]; then
    BYPASS=true
  fi
done

if ! $BYPASS && [[ "$(hostname)" != midway2* ]]; then
  echo "This script can only be run on Midway2. Exiting."
  exit 1
fi

module load namd

mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-mini.conf" > "TCR_##-mini.log"

