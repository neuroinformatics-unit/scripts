# GPU Node Runner Scripts

Generalized scripts for running arbitrary Python scripts across all available GPU nodes in an HPC cluster.


## Usage

```bash
bash scripts/run_on_all_gpu_nodes.sh your_script.py my_env miniconda/24.1
```

**Arguments:**
- `python_script` (required): Path to Python script to run
- `conda_env` (required): Conda environment name 
- `module_name` (optional): Module to load (default: `miniconda`)