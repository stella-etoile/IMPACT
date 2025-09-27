#!/bin/sh

#SBATCH --job-name=TCR_##-gamd-equil
#SBATCH --exclusive
#SBATCH --time=32:00:00
#SBATCH --partition=caslake
#SBATCH --nodes=8
#SBATCH --ntasks-per-node=48
#SBATCH --account=pi-haddadian


ulimit -l unlimited


# module load namd
module load namd/2.14+intel-2022.0+cuda-11.5

# mpiexec.hydra -bootstrap=slurm namd2 "TCR_##-gamd-equil.conf" > "TCR_##-gamd-equil.log"
charmrun +idlepoll +p32 +setcpuaffinity namd2 +devices 0,1,2,3 'TCR_##-gamd-equil.conf'  > 'TCR_##-gamd-equil.log'
