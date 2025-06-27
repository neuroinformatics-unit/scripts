#!/bin/bash

# This script runs the cellfinder portion of brainmapper twice.
# One run is from the main branch and the other is from a feature branch.
# The -k flag can be used to keep the directory after the script finishes.
# Resolution must be provided as one arg with quotes separated by spaces, e.g. "5 2 2"
# The comparison script is found at scripts/compare_cellfinder_output.py
# Usage: compare_cellfinder_output.sh [-k] <pr_number> <signal_path> <background_path> <resolution> [<comparison_script_path>]

set -e

KEEP_DIR=false

# Check if the script is run with the -d flag for dry run
while getopts "k" flag; do
  case "${flag}" in
    k) KEEP_DIR=true ;;
    *) echo "Usage: $0 [-k] <pr_number> <signal_path> <background_path> <resolution> <comparison_script_path>"
       exit 1 ;;
  esac
done

PR_NUMBER=${@:$OPTIND:1}
SIGNAL_PATH=${@:$OPTIND+1:1}
BACKGROUND_PATH=${@:$OPTIND+2:1}
RESOLUTION=${@:$OPTIND+3:1}
COMPARISON_SCRIPT=${@:$OPTIND+4:1}

if [[ -z "$PR_NUMBER" || -z "$SIGNAL_PATH" || -z "$BACKGROUND_PATH" || -z "$RESOLUTION" || -z "$COMPARISON_SCRIPT" ]]; then
    echo "Usage: $0 [-k] <pr_number> <signal_path> <background_path> <resolution> <comparison_script_path>"
    exit 1
fi

echo "Comparing cellfinder correctness between main and PR $PR_NUMBER"

echo "Cloning cellfinder repository and setting up environment..."
# Make a new directory to store the results
mkdir -p $HOME/.cellfinder_comparison_$PR_NUMBER
cd $HOME/.cellfinder_comparison_$PR_NUMBER

if [ -d "cellfinder" ]; then
    echo "cellfinder directory already exists"
    git -C cellfinder checkout main
    git -C cellfinder pull
else
    echo "Cloning cellfinder repository..."
    git clone https://github.com/brainglobe/cellfinder.git
fi

source ~/.bash_profile
conda activate
conda create -n cellfinder_comparison python=3.12 -y
conda activate cellfinder_comparison

pip install brainglobe-workflows
pip install ./cellfinder -U

echo "Running cellfinder from the main branch..."
brainmapper -s $SIGNAL_PATH -b $BACKGROUND_PATH -o ./cellfinder_main -v $RESOLUTION --orientation apl --no-register --no-analyse --no-figures

git -C cellfinder fetch origin pull/$PR_NUMBER/head:$PR_NUMBER-branch
git -C cellfinder checkout $PR_NUMBER-branch

echo "Reinstalling cellfinder from the PR branch to account for dependency changes"
pip install ./cellfinder -U

echo "Running cellfinder from the PR branch..."
brainmapper -s $SIGNAL_PATH -b $BACKGROUND_PATH -o ./cellfinder_$PR_NUMBER -v $RESOLUTION --orientation apl --no-register --no-analyse --no-figures

echo "Comparing the results..."
python $COMPARISON_SCRIPT $PR_NUMBER

echo "Cleaning up the environment..."
conda deactivate
conda env remove -n cellfinder_comparison -y -q

if [ "$KEEP_DIR" = false ]; then
    cd $HOME
    echo "Removing the temporary directory..."
    rm -rf .cellfinder_comparison_$PR_NUMBER
fi
