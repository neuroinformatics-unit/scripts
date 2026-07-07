#!/usr/bin/env bash
# SBATCH directives - run arbitrary Python script on GPU node
#SBATCH --job-name=gpu_python_runner
#SBATCH --output=logs/gpu_python_runner_%j.out
#SBATCH --error=logs/gpu_python_runner_%j.err
#SBATCH --time=00:05:00
#SBATCH --partition=gpu
#SBATCH --gres=gpu:1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G

set -euo pipefail

# Check if Python script path is provided
if [ "$#" -lt 1 ]; then
    echo "ERROR: No Python script provided"
    echo "Usage: $0 <python_script.py> [conda_env] [module_name]"
    exit 1
fi

PYTHON_SCRIPT="$1"
CONDA_ENV="$2"
MODULE_NAME="${3:-miniconda}"

# Verify the Python script exists
if [ ! -f "${PYTHON_SCRIPT}" ]; then
    echo "ERROR: Python script not found: ${PYTHON_SCRIPT}"
    exit 1
fi

echo "Starting Python script execution on GPU node"
echo "Hostname: $(hostname)"
echo "Date: $(date --iso-8601=seconds)"
echo "Python script: ${PYTHON_SCRIPT}"
echo "Conda environment: ${CONDA_ENV}"
echo "Module: ${MODULE_NAME}"
echo ""

# Ensure modules system is available
source /etc/profile.d/modules.sh

echo "Loading module: ${MODULE_NAME}..."
module load "${MODULE_NAME}" 

echo "Activating conda environment: ${CONDA_ENV}"
conda activate "${CONDA_ENV}"

echo "Python version:" $(python -V 2>&1)
echo ""

echo "nvidia-smi output (brief):" 
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "nvidia-smi query failed"
else
    echo "nvidia-smi not available"
fi

echo ""
echo "=========================================="
echo "Running Python script: ${PYTHON_SCRIPT}"
echo "=========================================="
echo ""

# Execute the provided Python script
python "${PYTHON_SCRIPT}"

EXIT_CODE=$?

echo ""
echo "=========================================="
if [ ${EXIT_CODE} -eq 0 ]; then
    echo "Script completed successfully ✓"
else
    echo "Script failed with exit code: ${EXIT_CODE}"
fi
echo "=========================================="

exit ${EXIT_CODE}
