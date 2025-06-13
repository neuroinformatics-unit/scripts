#!/bin/bash

set -e

ORG="$1"
DEPENDENCY="$2"
NEW_VERSION="$3"
REVIEWER="$4"
BRANCH_NAME="update-${DEPENDENCY}-pin-${NEW_VERSION}"

if [[ -z "$ORG" || -z "$DEPENDENCY" || -z "$NEW_VERSION" || -z "$REVIEWER" ]]; then
  echo "Usage: $0 <org> <dependency> <new_version> <reviewer>"
  exit 1
fi

gh repo list "$ORG" --json nameWithOwner --limit 1000 | \
  jq -r '.[].nameWithOwner' | while read -r REPO; do
    REPO_URL="https://github.com/${REPO}.git"
    BRANCH_NAME="update-${DEPENDENCY}-pin-${NEW_VERSION}"
    REPO_NAME=$(basename -s .git "$REPO_URL")

    git clone "$REPO_URL"
    cd "$REPO_NAME"

  if grep -qE "^[[:space:]]*\"$DEPENDENCY([[:space:]]|>|\"|\!|<|=)" pyproject.toml; then
    git checkout -b "$BRANCH_NAME"
    sed -i -E "/^[[:space:]]*\"${DEPENDENCY}( |>|<|=|!)/c\    \"${DEPENDENCY}${NEW_VERSION}\"," pyproject.toml
    git add pyproject.toml
    git commit -m "Update ${DEPENDENCY} to version ${NEW_VERSION}"
    git push origin "$BRANCH_NAME"
    echo "Dependency updated and pushed to branch $BRANCH_NAME."

    gh pr create --base main --head "$BRANCH_NAME" --title "Update ${DEPENDENCY} to ${NEW_VERSION}" --body "This PR updates the ${DEPENDENCY} dependency to version ${NEW_VERSION}." --reviewer "$REVIEWER"
  else
    echo "Dependency ${DEPENDENCY} not found in pyproject.toml. No changes made."
  fi

  cd ..
  rm -rf "$REPO_NAME"
done