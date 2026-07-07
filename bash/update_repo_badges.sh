#!/usr/bin/env bash

set -euo pipefail

ORG="brainglobe"
BRANCH_NAME="update/standardize-readme-badges"
PR_TITLE="docs: standardise README badge block"
PR_BODY="Standardises the README badge section across BrainGlobe repos"
WORK_DIR="$(pwd)/.brainglobe_badge_work"
DRY_RUN=false
ONLY_REPO=""

REPOS=(
    "brainglobe-atlasapi"
"brainglobe-ccf-translator"
"brainglobe-data-api-connectivity"
"brainglobe-data-api-volume"
"brainglobe-heatmap"
"brainglobe-napari-io"
"brainglobe-registration"
"brainglobe-segmentation"
"brainglobe-space"
"brainglobe-stitch"
"brainglobe-template-builder"
"brainglobe-utils"
"brainglobe-workflows"
"brainreg"
"brainrender"
"brainrender-napari"
"cellfinder"
"morphapi"
)

# parsing args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true ; shift ;;
        --repo)     ONLY_REPO="$2" ; shift 2 ;;
        *) echo "Unknown argument: $1" ; exit 1 ;;
    esac
done

log()  { echo "[INFO]  $*" ; }
warn() { echo "[WARN]  $*" >&2 ; }
die()  { echo "[ERROR] $*" >&2 ; exit 1 ; }

require_cmd() {
    command -v "$1" &>/dev/null || die "'$1' is required but not found in PATH."
}

require_cmd git
require_cmd gh
require_cmd python3

mkdir -p "$WORK_DIR"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_HELPER="$SCRIPT_DIR/../python/badge_updater.py"
[[ -f "$PYTHON_HELPER" ]] || die "Cannot find Python helper: $PYTHON_HELPER"

process_repo() {
    local repo="$1"
    local repo_dir="$WORK_DIR/$repo"

    log "Processing: $ORG/$repo"

    # 1.Clone/update
    if [[ -d "$repo_dir/.git" ]]; then
        log "Repo exists locally, resetting to origin/main…"
        git -C "$repo_dir" fetch origin --prune
        git -C "$repo_dir" checkout main 2>/dev/null \
            || git -C "$repo_dir" checkout master 2>/dev/null \
            || { warn "Cannot find main/master for $repo - skipping."; return 0; }
        git -C "$repo_dir" reset --hard origin/HEAD
    else
        log "Cloning $ORG/$repo…"
        if ! gh repo clone "$ORG/$repo" "$repo_dir" -- --depth=1 2>&1; then
            warn "Could not clone $ORG/$repo - skipping."
            return 0
        fi
    fi

    # 2.Find README
    local readme=""
    for candidate in README.md readme.md; do
        if [[ -f "$repo_dir/$candidate" ]]; then
            readme="$repo_dir/$candidate"
            break
        fi
    done

    if [[ -z "$readme" ]]; then
        warn "No README found in $repo - skipping."
        return 0
    fi

    log "README: $readme"

    # 3.Check if branch already exists remotely
    if git -C "$repo_dir" ls-remote --exit-code --heads origin "$BRANCH_NAME" &>/dev/null; then
        warn "Branch '$BRANCH_NAME' already exists on $repo - skipping."
        return 0
    fi

    # 4.Create branch
    git -C "$repo_dir" checkout -b "$BRANCH_NAME"

    # 5.Run badge_updater.py
    log "Running badge updater…"
    if ! python3 "$PYTHON_HELPER" "$readme" "$repo" "$ORG"; then
        warn "Badge updater failed for $repo - skipping."
        git -C "$repo_dir" checkout -f main 2>/dev/null || true
        git -C "$repo_dir" branch -D "$BRANCH_NAME" 2>/dev/null || true
        return 0
    fi

    # 6.Check for actual diff
    if git -C "$repo_dir" diff --quiet; then
        log "No changes needed for $repo - skipping PR."
        git -C "$repo_dir" checkout -f main 2>/dev/null || true
        git -C "$repo_dir" branch -D "$BRANCH_NAME" 2>/dev/null || true
        return 0
    fi

    log "Diff preview (README only):"
    git -C "$repo_dir" diff -- "$(basename "$readme")" || true

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would commit, push, and open PR for $repo."
        git -C "$repo_dir" checkout -f main 2>/dev/null || true
        git -C "$repo_dir" branch -D "$BRANCH_NAME" 2>/dev/null || true
        return 0
    fi

    # 7.Commit
    git -C "$repo_dir" add "$(basename "$readme")"
    git -C "$repo_dir" commit -m "docs: standardise README badge block"

    # 8.Push
    log "Pushing branch $BRANCH_NAME to origin…"
    git -C "$repo_dir" push origin "$BRANCH_NAME"

    # 9.Open PR
    log "Opening PR…"
    gh pr create \
        --repo "$ORG/$repo" \
        --head "$BRANCH_NAME" \
        --base main \
        --title "$PR_TITLE" \
        --body "$PR_BODY" \
        --label "documentation" \
    && log "PR opened for $repo." \
    || warn "PR creation failed for $repo (maybe label doesn't exist - try without --label)."

    log "Done: $repo"
}

# Main
if [[ -n "$ONLY_REPO" ]]; then
    process_repo "$ONLY_REPO"
else
    for repo in "${REPOS[@]}"; do
        process_repo "$repo" || warn "Unhandled error for $repo - continuing."
    done
fi

log "All repos processed."
log "Work directory: $WORK_DIR"