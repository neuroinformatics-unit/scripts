#!/usr/bin/env bash
set -euo pipefail

ORG="brainglobe"
BRANCH="migrate/tox-to-uv-action"
PR_TITLE="ci: migrate from tox to uv test action"
PR_BODY='Migrate CI from `neuroinformatics-unit/actions/test@v2` (tox) to `neuroinformatics-unit/actions/test-uv@main` (pure uv).'

WORK_DIR="$(pwd)/.uv_migration_work"
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

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true;         shift ;;
        --repo)    ONLY_REPO="$2";       shift 2 ;;
        --org)     ORG="$2";             shift 2 ;;
        *) echo "Unknown argument: $1"; exit 1 ;;
    esac
done

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*" >&2; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

command -v git     &>/dev/null || die "git not found in PATH"
command -v gh      &>/dev/null || die "gh not found - install GitHub CLI"
command -v python3 &>/dev/null || die "python3 not found in PATH"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_HELPER="$SCRIPT_DIR/../python/migrate_to_uv.py"
[[ -f "$PYTHON_HELPER" ]] || die "Python helper not found: $PYTHON_HELPER"

mkdir -p "$WORK_DIR"

process_repo() {
    local repo="$1"
    local repo_dir="$WORK_DIR/$repo"

    #1. Clone or reset to latest main
    if [[ -d "$repo_dir/.git" ]]; then
        log "Resetting existing clone to origin/main…"
        git -C "$repo_dir" fetch origin --prune --quiet
        git -C "$repo_dir" checkout main 2>/dev/null \
            || git -C "$repo_dir" checkout master 2>/dev/null \
            || { warn "Cannot find main/master in $repo - skipping."; return 0; }
        git -C "$repo_dir" reset --hard origin/HEAD --quiet
    else
        log "Cloning $ORG/$repo…"
        gh repo clone "$ORG/$repo" "$repo_dir" -- --depth=1 --quiet 2>&1 \
            || { warn "Clone failed for $repo - skipping."; return 0; }
    fi

    #2. Skip if migration branch already exists
    if git -C "$repo_dir" ls-remote --exit-code --heads origin "$BRANCH" &>/dev/null; then
        warn "Branch '$BRANCH' already exists on remote - skipping $repo."
        return 0
    fi

    #3. Locate files
    local workflow="$repo_dir/.github/workflows/test_and_deploy.yml"
    local pyproject="$repo_dir/pyproject.toml"

    if [[ ! -f "$workflow" && ! -f "$pyproject" ]]; then
        warn "Neither workflow nor pyproject.toml found - skipping $repo."
        return 0
    fi

    #4. Create migration branch
    git -C "$repo_dir" checkout -b "$BRANCH" --quiet

    #5. Run Python helper
    log "Running migration script…"
    local exit_code=0
    python3 "$PYTHON_HELPER" "$workflow" "$pyproject" || exit_code=$?

    case $exit_code in
        0)  log "Migration script made changes." ;;
        2)  log "Nothing to migrate in $repo - skipping PR."
            git -C "$repo_dir" checkout -f main    --quiet 2>/dev/null || true
            git -C "$repo_dir" branch -D "$BRANCH" --quiet 2>/dev/null || true
            return 0 ;;
        *)  warn "Migration script failed (exit $exit_code) - skipping $repo."
            git -C "$repo_dir" checkout -f main    --quiet 2>/dev/null || true
            git -C "$repo_dir" branch -D "$BRANCH" --quiet 2>/dev/null || true
            return 0 ;;
    esac

    #6. Verify there is an actual diff
    if git -C "$repo_dir" diff --quiet; then
        log "No file diff despite script success - skipping PR."
        git -C "$repo_dir" checkout -f main    --quiet 2>/dev/null || true
        git -C "$repo_dir" branch -D "$BRANCH" --quiet 2>/dev/null || true
        return 0
    fi

    log "Diff preview:"
    git -C "$repo_dir" diff || true

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would commit, push, and open PR for $repo."
        log "[DRY RUN] Changes have been left in:"
        log "          $repo_dir"
        log "Inspect them with:"
        log "  git -C \"$repo_dir\" diff"
        return 0
    fi

    #7. Stage only the two files
    [[ -f "$workflow"   ]] && \
        git -C "$repo_dir" add ".github/workflows/test_and_deploy.yml" 2>/dev/null || true
    [[ -f "$pyproject"  ]] && \
        git -C "$repo_dir" add "pyproject.toml" 2>/dev/null || true

    if git -C "$repo_dir" diff --cached --quiet; then
        warn "Nothing staged after add - skipping $repo."
        git -C "$repo_dir" checkout -f main --quiet 2>/dev/null || true
        git -C "$repo_dir" branch -D "$BRANCH" --quiet 2>/dev/null || true
        return 0
    fi

    #8. Commit
    git -C "$repo_dir" commit -m "ci: migrate from tox to uv test action" --quiet
    log "Committed changes."

    #9. Push
    log "Pushing branch '$BRANCH'…"
    git -C "$repo_dir" push origin "$BRANCH" --quiet

    #10. Open PR
    log "Opening PR…"
    if gh pr create \
        --repo  "$ORG/$repo" \
        --head  "$BRANCH" \
        --base  main \
        --title "$PR_TITLE" \
        --body  "$PR_BODY"; then
        log "PR opened for $repo."
    else
        warn "PR creation failed for $repo (check gh auth or if PR already exists)."
    fi
}

if [[ -n "$ONLY_REPO" ]]; then
    process_repo "$ONLY_REPO"
else
    for repo in "${REPOS[@]}"; do
        process_repo "$repo" || warn "Unhandled error for $repo - continuing."
        echo
    done
fi

log "Completed: $WORK_DIR"