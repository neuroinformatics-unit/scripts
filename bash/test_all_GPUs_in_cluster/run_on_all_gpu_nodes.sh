#!/usr/bin/env bash
# Wrapper script to submit Python script execution to ALL GPU nodes
# Tests across all available GPU partitions (gpu, gpu_lowp, a100)

set -euo pipefail

# Check arguments
if [ "$#" -lt 1 ]; then
    echo "ERROR: No Python script provided"
    echo ""
    echo "Usage: $0 <python_script.py> [conda_env] [module_name]"
    echo ""
    echo "Arguments:"
    echo "  python_script.py  - Path to Python script to run on GPU nodes"
    echo "  conda_env         - Conda environment name"
    echo "  module_name       - Module to load before conda (default: miniconda)"
    echo ""
    echo "Examples:"
    echo "  $0 test_pytorch.py"
    echo "  $0 test_pytorch.py my_env"
    echo "  $0 benchmark.py my_env miniconda/24.1"
    exit 1
fi

PYTHON_SCRIPT="$1"
CONDA_ENV="$2"
MODULE_NAME="${3:-miniconda}"

# Generate job prefix from script name (remove .py extension and path)
SCRIPT_BASENAME=$(basename "${PYTHON_SCRIPT}" .py)
JOB_PREFIX="${SCRIPT_BASENAME}"

# Verify the Python script exists
if [ ! -f "${PYTHON_SCRIPT}" ]; then
    echo "ERROR: Python script not found: ${PYTHON_SCRIPT}"
    exit 1
fi

# Get absolute path for the script
PYTHON_SCRIPT_ABS=$(readlink -f "${PYTHON_SCRIPT}")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SBATCH_SCRIPT="${SCRIPT_DIR}/gpu_node_runner.sh"

if [ ! -f "${SBATCH_SCRIPT}" ]; then
    echo "ERROR: sbatch script not found: ${SBATCH_SCRIPT}"
    exit 1
fi

# Create logs directory if it doesn't exist
LOGS_DIR="${SCRIPT_DIR}/../logs"
mkdir -p "${LOGS_DIR}"

echo "=========================================="
echo "GPU Node Python Script Runner"
echo "=========================================="
echo "Python script: ${PYTHON_SCRIPT_ABS}"
echo "Conda environment: ${CONDA_ENV}"
echo "Module: ${MODULE_NAME}"
echo "Job name: ${JOB_PREFIX}"
echo ""

echo "Discovering GPU nodes from all partitions (gpu, gpu_lowp, a100)..."

# Get all unique GPU nodes from gpu, gpu_lowp, and a100 partitions
GPU_NODES=$(sinfo -N -o "%N %G %P %T" | \
    grep "^gpu-" | \
    grep -v "down" | \
    grep -E "(gpu|gpu_lowp|a100)" | \
    awk '{print $1}' | \
    sort -u)

if [ -z "${GPU_NODES}" ]; then
    echo "ERROR: No GPU nodes found"
    exit 1
fi

NODE_COUNT=$(echo "${GPU_NODES}" | wc -l)
echo "Found ${NODE_COUNT} unique GPU nodes to test"
echo ""

# Track submitted jobs and failed nodes
SUBMITTED_JOBS=()
FAILED_NODES=()

# Get partition for each node
declare -A NODE_PARTITION

set +u  # Disable unbound variable check for associative array operations
while read -r line; do
    node=$(echo "$line" | awk '{print $1}')
    partition=$(echo "$line" | awk '{print $3}')
    # Prefer specific partitions over generic 'gpu'
    if [[ "$partition" == "a100" ]] || [[ "$partition" == "gpu_lowp" ]]; then
        NODE_PARTITION[$node]=$partition
    elif [[ -z "${NODE_PARTITION[$node]:-}" ]]; then
        NODE_PARTITION[$node]=$partition
    fi
done < <(sinfo -N -o "%N %G %P %T" | grep "^gpu-" | grep -v "down" | grep -E "(gpu|gpu_lowp|a100)")
set -u  # Re-enable

# Submit one job per GPU node with appropriate partition
set +u  # Temporarily disable unbound variable check for associative array
for node in ${GPU_NODES}; do
    # Get partition for this node, default to gpu if not set
    partition="${NODE_PARTITION[$node]:-gpu}"
    set -u  # Re-enable
    
    echo "Submitting job to node: ${node} (partition: ${partition})"
    
    # Submit with explicit nodelist and partition, passing script and environment
    JOB_OUTPUT="${LOGS_DIR}/${JOB_PREFIX}_${node}.out"
    JOB_ERROR="${LOGS_DIR}/${JOB_PREFIX}_${node}.err"
    
    JOB_RESULT=$(sbatch \
        --partition="${partition}" \
        --nodelist="${node}" \
        --output="${JOB_OUTPUT}" \
        --error="${JOB_ERROR}" \
        --job-name="${JOB_PREFIX}_${node}" \
        "${SBATCH_SCRIPT}" "${PYTHON_SCRIPT_ABS}" "${CONDA_ENV}" "${MODULE_NAME}" 2>&1)
    
    if echo "${JOB_RESULT}" | grep -q "Submitted batch job"; then
        JOB_ID=$(echo "${JOB_RESULT}" | awk '{print $NF}')
        SUBMITTED_JOBS+=("${JOB_ID}")
        echo "  -> Job ID: ${JOB_ID}"
    else
        FAILED_NODES+=("${node}")
        echo "  -> FAILED: ${JOB_RESULT}"
    fi
done

echo ""
echo "=========================================="
echo "Submitted ${#SUBMITTED_JOBS[@]} jobs successfully"
if [ ${#FAILED_NODES[@]} -gt 0 ]; then
    echo "Failed to submit to ${#FAILED_NODES[@]} nodes: ${FAILED_NODES[*]}"
fi
echo "Job IDs: ${SUBMITTED_JOBS[*]}"
echo ""
echo "Output files will be in: ${LOGS_DIR}/${JOB_PREFIX}_<node>.out"
echo "Error files will be in: ${LOGS_DIR}/${JOB_PREFIX}_<node>.err"
echo ""
echo "To monitor job status:"
echo "  squeue -u \$USER | grep ${JOB_PREFIX}"
echo "=========================================="
