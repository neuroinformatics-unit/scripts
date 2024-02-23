#!/bin/bash

#SBATCH -p gpu # partition
#SBATCH -N 1   # number of nodes
#SBATCH --mem 64G # memory pool for all cores
#SBATCH -n 2 # number of cores
#SBATCH -t 3-00:00 # time (D-HH:MM)
#SBATCH --gres gpu:1 # request 1 GPU (of any kind)
#SBATCH -o slurm_array.%N.%A-%a.out
#SBATCH -e slurm_array.%N.%A-%a.err
#SBATCH --mail-type=ALL
#SBATCH --mail-user=s.minano@ucl.ac.uk
#SBATCH --array=0-0%5


# NOTE on SBATCH command for array jobs
# with "SBATCH --array=0-n%m" ---> runs n separate jobs, but not more than m at a time.
# the number of array jobs should match the number of input files

# ---------------------------
# Github variables
# ---------------------------
KERAS_BACKEND=jax

# ---------------------------
# Define conda environment
# ---------------------------
module load miniconda

conda activate base
conda create -y -n cellfinder-keras3 python=3.10
conda activate cellfinder-keras3

which python
which pip

# python -m pip install --upgrade
python -m pip install "cellfinder[$KERAS_BACKEND] @ git+https://github.com/brainglobe/cellfinder.git@cellfinder-to-keras-3"


# -----------------------------------
# Input data: output from detection
# -----------------------------------




# ---------------------
# Run classification
# ---------------------