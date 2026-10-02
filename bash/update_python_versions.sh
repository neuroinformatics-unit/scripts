#!/usr/bin/env bash
# Update the supported Python versions across repositories (e.g. to follow SPEC 0)
# and open a PR for each one, so CI runs on the new versions and a human can review.
# Example of the resulting change: https://github.com/brainglobe/brainglobe-stitch/pull/78
#
# Requires git, python3 (>=3.11, for TOML validation) and an authenticated GitHub CLI (gh).
# Works on macOS and Linux (no GNU-specific sed).
#
# Usage: ./update_python_versions.sh [--min 3.12] [--max 3.14] [--dry-run]
#                                    [--repo <name>] [--org <org>] [--reviewer <user1,user2>]
#                                    [--issue <issue URL or org/repo#N>]
#
# The supported versions become every minor version from --min to --max inclusive.
# Files updated in each repository:
#   pyproject.toml
#     - requires-python = ">=3.X"
#     - "Programming Language :: Python :: 3.X" classifiers
#     - [tool.black] target-version = ['py3X', ...]  / [tool.ruff] target-version = "py3X"
#     - legacy tox config: envlist = py{3X,...} and the [gh-actions] "3.X: py3X" mapping
#   .github/workflows/*.yml / *.yaml
#     - only inside a `matrix:` block that lists >= 2 python versions: the version list,
#       plus `include:` entries pinned to the old newest (or a dropped) version.
#       Python versions pinned outside a test matrix are intentionally left alone.
# Any remaining references to dropped versions are printed and listed in the PR body
# for the reviewer to check by hand, as are workflow lines that pin a single supported
# Python version outside a test matrix (e.g. a docs or lint job on 3.12).
# If --issue is given, "Tracked in <issue>" is appended to the bottom of each PR body.
set -euo pipefail

ORG="brainglobe"
MIN_VERSION="3.12"
MAX_VERSION="3.14"
REVIEWER=""
ISSUE=""
DRY_RUN=false
ONLY_REPO=""

WORK_DIR="$(pwd)/.python_versions_work"

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

usage() {
    echo "Usage: $0 [--min 3.12] [--max 3.14] [--dry-run] [--repo <name>] [--org <org>] [--reviewer <users>] [--issue <issue>]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true;       shift ;;
        --repo)     ONLY_REPO="$2";     shift 2 ;;
        --org)      ORG="$2";           shift 2 ;;
        --min)      MIN_VERSION="$2";   shift 2 ;;
        --max)      MAX_VERSION="$2";   shift 2 ;;
        --reviewer) REVIEWER="$2";      shift 2 ;;
        --issue)    ISSUE="$2";         shift 2 ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "Unknown argument: $1"; usage; exit 1 ;;
    esac
done

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*" >&2; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

[[ "$MIN_VERSION" =~ ^3\.[0-9]+$ ]] || die "--min must look like 3.X (got '$MIN_VERSION')"
[[ "$MAX_VERSION" =~ ^3\.[0-9]+$ ]] || die "--max must look like 3.X (got '$MAX_VERSION')"
MIN_MINOR="${MIN_VERSION#3.}"
MAX_MINOR="${MAX_VERSION#3.}"
(( MIN_MINOR <= MAX_MINOR )) || die "--min ($MIN_VERSION) is newer than --max ($MAX_VERSION)"

command -v git     &>/dev/null || die "git not found in PATH"
command -v gh      &>/dev/null || die "gh not found - install GitHub CLI"
command -v python3 &>/dev/null || die "python3 not found in PATH"
if [[ "$DRY_RUN" != true ]]; then
    gh auth status &>/dev/null || die "gh is not authenticated - run 'gh auth login'"
fi

BRANCH="update-python-versions-${MIN_VERSION}-${MAX_VERSION}"
PR_TITLE="Update supported Python versions to ${MIN_VERSION}-${MAX_VERSION}"
COMMIT_MSG="Update supported Python versions to ${MIN_VERSION}-${MAX_VERSION} (SPEC 0)"

# Regexes matching a dropped version, e.g. "3.11" or "py311" (for MIN=3.12, covers 3.8-3.11).
# Surrounding-character checks avoid matching things like "1.3.11" or "3.110".
DROPPED_MINORS=""
for (( m = 8; m < MIN_MINOR; m++ )); do
    DROPPED_MINORS+="${DROPPED_MINORS:+|}$m"
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_HELPER="$SCRIPT_DIR/../python/update_python_versions.py"
[[ -f "$PYTHON_HELPER" ]] || die "Python helper not found: $PYTHON_HELPER"

mkdir -p "$WORK_DIR"

# Edit pyproject.toml and workflow files in place; single-version workflow pins
# that were left alone are written to the file given as $2.
# Exit codes: 0 = files changed, 2 = nothing to change, other = error.
apply_updates() {
    python3 "$PYTHON_HELPER" "$1" "$MIN_MINOR" "$MAX_MINOR" "$2"
}

# Print lines still referring to dropped Python versions (for manual review).
find_leftovers() {
    local repo_dir="$1"
    [[ -n "$DROPPED_MINORS" ]] || return 0
    git -C "$repo_dir" grep -nIE \
        "(^|[^0-9.])(3\.(${DROPPED_MINORS})|py3(${DROPPED_MINORS}))([^0-9]|$)" \
        -- '*.toml' '*.cfg' '*.ini' '*.yml' '*.yaml' '*.md' '*.rst' '*.txt' '.python-version' \
        || true
}

cleanup_branch() {
    local repo_dir="$1" base="$2"
    git -C "$repo_dir" checkout -f "$base" --quiet 2>/dev/null || true
    git -C "$repo_dir" branch -D "$BRANCH" --quiet 2>/dev/null || true
}

process_repo() {
    local repo="$1"
    local repo_dir="$WORK_DIR/$repo"
    log "===== $ORG/$repo"

    #1. Fresh clone of the default branch
    rm -rf "$repo_dir"
    if [[ "$DRY_RUN" == true ]]; then
        git clone --quiet --depth=1 "https://github.com/$ORG/$repo.git" "$repo_dir"
    else
        # gh uses the configured protocol and credentials, so the later push works
        gh repo clone "$ORG/$repo" "$repo_dir" -- --depth=1 --quiet
    fi || { warn "Clone failed for $repo - skipping."; return 0; }
    local base
    base="$(git -C "$repo_dir" symbolic-ref --short refs/remotes/origin/HEAD)"
    base="${base#origin/}"

    #2. Skip if the branch or an open PR from it already exists
    if git -C "$repo_dir" ls-remote --exit-code --heads origin "$BRANCH" &>/dev/null; then
        warn "Branch '$BRANCH' already exists on remote - skipping $repo."
        return 0
    fi

    #3. Create branch and apply the updates
    git -C "$repo_dir" checkout -b "$BRANCH" --quiet
    local exit_code=0 pins_file="$WORK_DIR/$repo.pins"
    rm -f "$pins_file"
    apply_updates "$repo_dir" "$pins_file" || exit_code=$?
    case $exit_code in
        0) ;;
        2) log "Nothing to update in $repo - skipping PR."
           cleanup_branch "$repo_dir" "$base"
           return 0 ;;
        *) warn "Update failed (exit $exit_code) - skipping $repo."
           cleanup_branch "$repo_dir" "$base"
           return 0 ;;
    esac

    log "Diff preview:"
    git -C "$repo_dir" --no-pager diff

    #4. Anything left behind that mentions a dropped version?
    local leftovers
    leftovers="$(find_leftovers "$repo_dir")"
    if [[ -n "$leftovers" ]]; then
        warn "References to dropped Python versions remain in $repo (not changed):"
        echo "$leftovers" >&2
    fi
    local pins=""
    [[ -f "$pins_file" ]] && pins="$(cat "$pins_file")"
    if [[ -n "$pins" ]]; then
        warn "Workflows in $repo pin a single Python version outside a test matrix (not changed):"
        echo "$pins" >&2
    fi

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would commit, push, and open a PR against '$base'."
        log "[DRY RUN] Changes left in: $repo_dir"
        return 0
    fi

    #5. Commit and push
    git -C "$repo_dir" add -u
    if git -C "$repo_dir" diff --cached --quiet; then
        warn "Nothing staged - skipping $repo."
        return 0
    fi
    git -C "$repo_dir" commit --quiet -m "$COMMIT_MSG"
    git -C "$repo_dir" push --quiet origin "$BRANCH"

    #6. Open the PR
    local body
    body="Update the supported Python versions to ${MIN_VERSION}-${MAX_VERSION}, following [SPEC 0](https://scientific-python.org/specs/spec-0000/).

- Bump \`requires-python\` to \`>=${MIN_VERSION}\`
- Update the Python version classifiers and tool target versions
- Update the CI test matrix to Python ${MIN_VERSION}-${MAX_VERSION} (other OSes on \`${MAX_VERSION}\`)

This PR was opened by a script. Please check that CI passes on the new Python versions before merging."
    if [[ -n "$leftovers" ]]; then
        body+="

**Please review:** these lines still mention a dropped Python version and were not changed automatically:
\`\`\`
${leftovers}
\`\`\`"
    fi
    if [[ -n "$pins" ]]; then
        body+="

**Please review:** these workflow lines pin a single Python version outside the test matrix and were not changed automatically:
\`\`\`
${pins}
\`\`\`"
    fi
    if [[ -n "$ISSUE" ]]; then
        body+="

Tracked in ${ISSUE}"
    fi

    local pr_args=(--repo "$ORG/$repo" --head "$BRANCH" --base "$base" --title "$PR_TITLE" --body "$body")
    [[ -n "$REVIEWER" ]] && pr_args+=(--reviewer "$REVIEWER")
    if gh pr create "${pr_args[@]}"; then
        log "PR opened for $repo."
    else
        warn "PR creation failed for $repo."
    fi
}

log "Supported Python versions: ${MIN_VERSION}-${MAX_VERSION} (branch: $BRANCH, dry run: $DRY_RUN)"
if [[ -n "$ONLY_REPO" ]]; then
    process_repo "$ONLY_REPO"
else
    for repo in "${REPOS[@]}"; do
        process_repo "$repo" || warn "Unhandled error for $repo - continuing."
        echo
    done
fi

log "Completed: $WORK_DIR"
