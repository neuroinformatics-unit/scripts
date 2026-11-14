#!/usr/bin/env bash
# Pin third-party GitHub Actions to commit SHAs in each repository and open a PR.
# Our own actions stay on their major version tag (e.g. @v3). No versions are upgraded.
#
# Requires git, pinact, python3 with PyYAML, and gh (not needed for --dry-run).
#
# Usage: ./pin_actions_to_sha.sh [--dry-run] [--repo <name>] [--org <org>]
#                                [--workflows-only] [--reviewer <user1,user2>]
#                                [--issue <issue URL or org/repo#N>]
#
# Exits with 1 if any repository fails.
set -euo pipefail

ORG="neuroinformatics-unit"
REVIEWER=""
ISSUE=""
DRY_RUN=false
ONLY_REPO=""
WORKFLOWS_ONLY=false

WORK_DIR="$(pwd)/.pin_actions_work"

# "actions" and "movement" are already done
REPOS=(
"datashuttle"
"ethology"
"HowTo"
"NeuroBlueprint"
"neuroinformatics-unit.github.io"
"photon-mosaic"
"python-cookiecutter"
"spikewrap"
)

usage() {
    echo "Usage: $0 [--dry-run] [--repo <name>] [--org <org>] [--workflows-only] [--reviewer <users>] [--issue <issue>] [--list-repos]"
}

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*" >&2; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

need_value() { [[ $# -ge 2 && -n "$2" ]] || die "$1 requires a value"; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)        DRY_RUN=true;        shift ;;
        --repo)           need_value "$@"; ONLY_REPO="$2"; shift 2 ;;
        --org)            need_value "$@"; ORG="$2";       shift 2 ;;
        --workflows-only) WORKFLOWS_ONLY=true; shift ;;
        --reviewer)       need_value "$@"; REVIEWER="$2";  shift 2 ;;
        --issue)          need_value "$@"; ISSUE="$2";     shift 2 ;;
        # Used by the workflow
        --list-repos)     (IFS=,; echo "${REPOS[*]}"); exit 0 ;;
        -h|--help)        usage; exit 0 ;;
        *) echo "Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

# Names are used in paths and URLs, so check them
if [[ ! "$ORG" =~ ^[A-Za-z0-9-]+$ ]]; then
    die "--org is not a valid GitHub organisation name: '$ORG'"
fi
if [[ -n "$ONLY_REPO" ]]; then
    if [[ ! "$ONLY_REPO" =~ ^[A-Za-z0-9_.-]+$ || "$ONLY_REPO" == "." || "$ONLY_REPO" == ".." ]]; then
        die "--repo takes a single repository name (without the org), got '$ONLY_REPO'"
    fi
fi

command -v git     &>/dev/null || die "git not found in PATH"
command -v pinact  &>/dev/null || die "pinact not found - see https://github.com/suzuki-shunsuke/pinact#install"
command -v python3 &>/dev/null || die "python3 not found in PATH"
python3 -c "import yaml" &>/dev/null || die "PyYAML not found - run 'pip install pyyaml'"
if [[ "$DRY_RUN" != true ]]; then
    command -v gh &>/dev/null || die "gh not found - install GitHub CLI"
    gh auth status &>/dev/null || die "gh is not authenticated - run 'gh auth login'"
fi
# pinact needs GITHUB_TOKEN to avoid rate limits
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    if [[ -n "${GH_TOKEN:-}" ]]; then
        export GITHUB_TOKEN="$GH_TOKEN"
    elif command -v gh &>/dev/null && token="$(gh auth token 2>/dev/null)" && [[ -n "$token" ]]; then
        export GITHUB_TOKEN="$token"
    else
        warn "GITHUB_TOKEN is not set - pinact may hit GitHub API rate limits."
    fi
fi

BRANCH="pin-actions-to-sha"
PR_TITLE="Pin GitHub Actions to commit SHAs"
COMMIT_MSG="Pin third-party GitHub Actions to commit SHAs"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPENDABOT_HELPER="$SCRIPT_DIR/../python/check_dependabot_actions.py"
[[ -f "$DEPENDABOT_HELPER" ]] || die "Python helper not found: $DEPENDABOT_HELPER"

mkdir -p "$WORK_DIR"
SUMMARY=()
FAILED=()

# `set -e` is off inside process_repo, so each step reports failures here
fail() {
    warn "$2 - skipping $1."
    FAILED+=("$1: $2")
}

# Skips our own actions. Exit code 2 (some refs not pinned) is not a failure.
run_pinact() {
    local repo_dir="$1"; shift
    local code=0
    (cd "$repo_dir" && pinact run --exclude "(?i)^${ORG}/" "$@") || code=$?
    [[ $code -eq 0 || $code -eq 2 ]] || return "$code"
}

extra_files() {
    git -C "$1" grep -lE 'uses:[[:space:]]*["'\'']?[A-Za-z0-9_.-]+/[^[:space:]]+@' \
        -- '*.yml' '*.yaml' '*.md' \
        ':!.github/workflows/' ':!action.yml' ':!action.yaml' \
        ':!**/action.yml' ':!**/action.yaml' 2>/dev/null || true
}

# List `uses:` references that are still not pinned
unpinned_refs() {
    local repo_dir="$1" line location target ref owner
    local re='uses:[[:space:]]*["'\'']?([^"'\''`[:space:]#]+)'
    while IFS= read -r line; do
        location="${line%%:*}"
        line="${line#*:}"
        location="$location:${line%%:*}"
        line="${line#*:}"
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ "$line" =~ $re ]] || continue
        target="${BASH_REMATCH[1]}"
        case "$target" in
            ./*|docker://*|\$\{\{*) continue ;;
            *@*) ;;
            *) continue ;;
        esac
        ref="${target##*@}"
        owner="${target%%/*}"
        [[ "$ref" =~ ^[0-9a-f]{40}$ ]] && continue
        if [[ "$(printf '%s' "$owner" | tr '[:upper:]' '[:lower:]')" == \
              "$(printf '%s' "$ORG" | tr '[:upper:]' '[:lower:]')" ]]; then
            [[ "$ref" =~ ^v[0-9]+$ ]] && continue
            # Flag own actions only in workflow and action files, not docs
            case "${location%%:*}" in
                .github/workflows/*|action.yml|action.yaml|*/action.yml|*/action.yaml) ;;
                *) continue ;;
            esac
            echo "$location: $target (own action, not on a major version tag)"
        else
            echo "$location: $target (not pinned to a SHA)"
        fi
    done < <(git -C "$repo_dir" grep -nE 'uses:' -- '*.yml' '*.yaml' '*.md' 2>/dev/null || true)
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

    #1. Clone
    rm -rf "$repo_dir"
    if [[ "$DRY_RUN" == true ]]; then
        git clone --quiet --depth=1 "https://github.com/$ORG/$repo.git" "$repo_dir"
    else
        gh repo clone "$ORG/$repo" "$repo_dir" -- --depth=1 --quiet
    fi || { fail "$repo" "Clone failed"; return 0; }
    local base
    if ! base="$(git -C "$repo_dir" symbolic-ref --short refs/remotes/origin/HEAD)"; then
        fail "$repo" "Could not determine the default branch (empty repository?)"
        return 0
    fi
    base="${base#origin/}"

    #2. Skip if the branch already exists
    local ls_remote=0
    git -C "$repo_dir" ls-remote --exit-code --heads origin "$BRANCH" &>/dev/null || ls_remote=$?
    if [[ $ls_remote -eq 0 ]]; then
        warn "Branch '$BRANCH' already exists on remote - skipping $repo."
        SUMMARY+=("$repo: skipped, branch '$BRANCH' already exists (open PR, or stale branch to delete?)")
        return 0
    elif [[ $ls_remote -ne 2 ]]; then
        # 2 means the branch does not exist
        fail "$repo" "Could not check the remote for branch '$BRANCH'"
        return 0
    fi

    #3. Create branch and pin
    if ! git -C "$repo_dir" checkout -b "$BRANCH" --quiet; then
        fail "$repo" "Could not create branch '$BRANCH'"
        return 0
    fi
    if ! run_pinact "$repo_dir"; then
        fail "$repo" "pinact failed (GitHub API error?)"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if [[ "$WORKFLOWS_ONLY" != true ]]; then
        local extras=() f
        while IFS= read -r f; do extras+=("$f"); done < <(extra_files "$repo_dir")
        if [[ ${#extras[@]} -gt 0 ]] && ! run_pinact "$repo_dir" "${extras[@]}"; then
            fail "$repo" "pinact failed on docs/example files"
            cleanup_branch "$repo_dir" "$base"
            return 0
        fi
    fi

    #4. Collect notes for the reviewer
    local leftovers dependabot review=""
    leftovers="$(unpinned_refs "$repo_dir")"
    if ! dependabot="$(python3 "$DEPENDABOT_HELPER" "$repo_dir")"; then
        fail "$repo" "Dependabot coverage check failed"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if [[ -n "$leftovers" ]]; then
        warn "References not pinned automatically in $repo:"
        echo "$leftovers" >&2
        review+="**Not pinned automatically** (e.g. branch references such as \`@main\`; pin these to the matching release by hand, or keep them deliberately):
\`\`\`
${leftovers}
\`\`\`
"
    fi
    if [[ -n "$dependabot" ]]; then
        warn "Dependabot coverage in $repo:"
        echo "$dependabot" >&2
        review+="
**Dependabot coverage:** without a \`github-actions\` entry for these, the pinned SHAs will not get update PRs:
\`\`\`
${dependabot}
\`\`\`
"
    fi

    if git -C "$repo_dir" diff --quiet; then
        log "Nothing to pin in $repo - skipping PR."
        if [[ -n "$leftovers$dependabot" ]]; then
            warn "No PR for $repo, so the warnings above are not tracked anywhere else."
            SUMMARY+=("$repo: nothing to pin, but see its warnings in the log (no PR to track them)")
        fi
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi

    log "Diff preview:"
    git -C "$repo_dir" --no-pager diff

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would commit, push, and open a PR against '$base'."
        log "[DRY RUN] Changes left in: $repo_dir"
        return 0
    fi

    #5. Commit and push
    if ! git -C "$repo_dir" add -u; then
        fail "$repo" "Staging failed"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if ! git -C "$repo_dir" commit --quiet -m "$COMMIT_MSG"; then
        fail "$repo" "Commit failed (is git user.name / user.email set?)"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if ! git -C "$repo_dir" push --quiet origin "$BRANCH"; then
        fail "$repo" "Push failed (does the token have write access, including workflows?)"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi

    #6. Open the PR
    local body
    body="Pin third-party GitHub Actions to full commit SHAs, so a moved or compromised upstream tag can't change what runs in our CI.

- Each \`uses:\` reference to a third-party action now points to a full 40-character commit SHA, with the version as a trailing comment (e.g. \`# v7.0.1\`). Dependabot reads that comment and keeps updating both.
- Every pin is the commit the existing tag already pointed to, so behaviour is unchanged. No versions are upgraded.
- Our own \`${ORG}\` actions are left on their major version tag (e.g. \`@v3\`), as agreed in neuroinformatics-unit/movement#1145.

Pinned with [pinact](https://github.com/suzuki-shunsuke/pinact). This PR was opened by a script. Please check that CI passes before merging."
    if [[ -n "$review" ]]; then
        body+="

### Please review
${review}"
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
        warn "PR creation failed for $repo, but branch '$BRANCH' is already pushed. Open the PR by hand, or delete the branch and rerun:"
        warn "    gh api -X DELETE repos/$ORG/$repo/git/refs/heads/$BRANCH"
        FAILED+=("$repo: branch pushed but PR creation failed")
    fi
}

log "Pinning actions to SHAs in $ORG (branch: $BRANCH, dry run: $DRY_RUN)"
if [[ -n "$ONLY_REPO" ]]; then
    REPOS=("$ONLY_REPO")
fi
for repo in "${REPOS[@]}"; do
    process_repo "$repo" || fail "$repo" "Unhandled error"
    echo
done

if [[ ${#SUMMARY[@]} -gt 0 ]]; then
    log "Needs attention:"
    printf '        %s\n' "${SUMMARY[@]}"
fi
log "Completed: $WORK_DIR"
if [[ ${#FAILED[@]} -gt 0 ]]; then
    warn "Failed:"
    printf '        %s\n' "${FAILED[@]}" >&2
    exit 1
fi
