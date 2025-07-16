#!/bin/bash

# Script to update a specific dependency version in all repositories of a GitHub organization
# Must be run on Linux with GitHub CLI (gh) installed and authenticated.
# Usage: ./update_dependency_pin.sh [-d] <org> <dependency> <new_version> <reviewer>
# Multiple reviewers can be specified by separating them with commas.
# Use the -d flag for a dry run, which will preview changes.
# The new version must include the operators (>, <, =, !) and the version number (e.g., >=1.0.0).
# The first 1000 repositories will be processed. Only non-archived repositories will be considered.
# This script assumes that the dependency is specified in the pyproject.toml file.
# The dependency must be on a separate line in the file:
# dependencies = [
#    "napari>=0.4.18, !=0.6.0",
#    "brainglobe-atlasapi",
#    "scipy",
#]
# Not on the same line as other dependencies:
# napari = ["brainglobe-utils[qt]", "napari[all]"]

set -e

DRY_RUN=false

# Check if the script is run with the -d flag for dry run
while getopts "d" flag; do
  case "${flag}" in
    d) DRY_RUN=true ;;
    *) echo "Usage: $0 [-d] <org> <dependency> <new_version> <reviewer>"
       exit 1 ;;
  esac
done

# Fetch the remaining positional arguments after the options
ORG=${@:$OPTIND:1}
DEPENDENCY=${@:$OPTIND+1:1}
NEW_VERSION=${@:$OPTIND+2:1}
REVIEWER=${@:$OPTIND+3:1}
BRANCH_NAME="update-${DEPENDENCY}-pin-${NEW_VERSION}"

echo "Dry run mode: $DRY_RUN"
echo "Organization: $ORG"
echo "Dependency: $DEPENDENCY"
echo "New Version: $NEW_VERSION"
echo "Reviewer: $REVIEWER"

if [[ -z "$ORG" || -z "$DEPENDENCY" || -z "$NEW_VERSION" || -z "$REVIEWER" ]]; then
  echo "Usage: $0 [-d] <org> <dependency> <new_version> <reviewer>"
  exit 1
fi

gh repo list "$ORG" --json nameWithOwner,isArchived \
  --jq '.[] | select(.isArchived==false) | .nameWithOwner' --limit 1000 |  \
  while read -r REPO; do
    REPO_URL="https://github.com/${REPO}.git"
    BRANCH_NAME="update-${DEPENDENCY}-pin-${NEW_VERSION}"
    REPO_NAME=$(basename -s .git "$REPO_URL")

    echo "Processing repository: $REPO_NAME"
    git clone -q "$REPO_URL"
    cd "$REPO_NAME"

    if [ ! -f "pyproject.toml" ]; then
      echo "pyproject.toml not found in $REPO_NAME. Skipping."
      cd ..
      rm -rf "$REPO_NAME"
      continue
    fi

  # Use grep to find if dependency exists in pyproject.toml
  # The regex matches any number of spaces,
  # followed by the quoted dependency name,
  # optionally followed by a version specifier (e.g., >=1.0.0, <2.0.0, etc.).
  # Must end with a double quote and comma.
  if grep -qE "^\s*\"${DEPENDENCY}(\[.*])*(\s|>|\!|<|=)*=*\s*([0-9]+.*[0-9]*.*[0-9]*)*\"," pyproject.toml; then
    git checkout -b "$BRANCH_NAME"
    # The sed command updates the version of the dependency in pyproject.toml
    # It uses the regex from above to find the line with the dependency and replace the version number.
    # -r allows extended regex syntax, and -i edits the file in place.
    # The regex is split into two parts: the dependency name with any
    # optional dependencies in square brackets, followed by anything after up to the
    # double quotes. The second group is replaced with the new version.
    # this sed command work only on GNU - sed is different on Macs.
    sed -i -r "s/(^\s*\"${DEPENDENCY}(\[.*])*)((\s|>|\!|<|=)*=*\s*([0-9]+.*[0-9]*.*[0-9]*)*\")/\1${NEW_VERSION}\"/g" pyproject.toml

    if $DRY_RUN; then
      echo "Dry run: Would update ${DEPENDENCY} to version ${NEW_VERSION} in ${REPO_NAME}/pyproject.toml"
      git --no-pager diff pyproject.toml
    else
      git add pyproject.toml
      git commit -m "Update ${DEPENDENCY} to version ${NEW_VERSION}"
      echo "Dependency updated and pushed to branch $BRANCH_NAME."
      git push -u origin "$BRANCH_NAME"
      gh pr create --base main --head "$BRANCH_NAME" --title "Pin ${DEPENDENCY} to ${NEW_VERSION}" --body "This PR pins ${DEPENDENCY} to version ${NEW_VERSION}." --reviewer "$REVIEWER"
    fi
  else
    echo "Dependency ${DEPENDENCY} not found in pyproject.toml. No changes made."
  fi

  cd ..
  rm -rf "$REPO_NAME"

done