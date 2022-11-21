#!/bin/bash

# automatic fetch and pull of git repositories
# usage: fetch_n_pull.sh

# folders have to be organized reflecting github structure:
# /path/to/github-organization/repository-name

# Example of folder: /Users/lauraporta/Source/github
echo "Enter the path to the folder containing the repositories:"
read folder

# retreive github users or organizations
folders=$(ls $folder)

for f in ${folders[@]}; do
    cd $folder/$f
    for repo in $(ls); do
        cd $repo
        echo "Pulling $repo"
        git pull
        cd ..
    done
done