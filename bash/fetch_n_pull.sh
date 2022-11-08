#!/bin/bash

# automatic fetch and pull of git repositories
# usage: fetch_n_pull.sh

# folders have to be organized reflecting github structure:
# /path/to/github-organization/repository-name


githubDom=("brainglobe" "neuroinformatics-unit" "SainsburyWellcomeCenter")

for dom in ${githubDom[@]}; do
    cd /home/lauraporta/Source/github/$dom
    for repo in $(ls); do
        cd $repo
        echo "Fetching $repo"
        git fetch
        echo "Pulling $repo"
        git pull
        cd ..
    done
done