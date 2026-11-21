#!/usr/bin/env bash
# Update the GitHub Actions references in each repository and open a PR:
#   - third-party actions are pinned to commit SHAs
#   - our own actions are moved to their latest major version tag (e.g. @v3)
#   - a Dependabot config is added if missing, for repositories that publish
#     to PyPI and for the organisation's website. Other repositories get a
#     suggested config in the PR body.
#
# Requires git, gh, uv and pinact.
#
# Usage: ./pin_actions_to_sha.sh [--dry-run] [--repo <name>] [--org <org>]
#                                [--workflows-only] [--reviewer <user1,user2>]
#                                [--issue <issue URL or org/repo#N>]
#                                [--add-dependabot <auto|always|never>]
#
# For another organisation, pass --org and edit REPOS below.
#
# Exits with 1 if any repository fails.
set -euo pipefail

ORG="neuroinformatics-unit"
SHARED_ACTIONS="neuroinformatics-unit/actions"
REVIEWER=""
ISSUE=""
DRY_RUN=false
ONLY_REPO=""
WORKFLOWS_ONLY=false
ADD_DEPENDABOT="auto"

WORK_DIR="$(pwd)/.pin_actions_work"

# "movement", "datashuttle" and "actions" are already done
REPOS=(
# Packages and tools
"dashboard"
"derotation"
"driftplots"
"ethology"
"fancylog"
"greendisc-toolkit"
"movement-figures"
"OSCaR"
"OSCaR-web-app"
"poseinterface"
"qt-niu"
"slurmio"
"spikesorted"
"spikesorted-spec"
"spikewrap"
# Websites, templates and org config
".github"
"NeuroBlueprint"
"neuroinformatics-unit.github.io"
"python-cookiecutter"
"quarto-presentation-template"
"software-practice-template"
# Courses
"course-animals-in-motion"
"course-intro-python"
"course-intro-scientific-python"
"course-large-array-data"
"course-linux-hpc"
"course-software-good-practice"
"course_ephys_osss"
"software-skills"
)

usage() {
    echo "Usage: $0 [--dry-run] [--repo <name>] [--org <org>] [--workflows-only] [--reviewer <users>] [--issue <issue>] [--add-dependabot <auto|always|never>]"
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
        --add-dependabot) need_value "$@"; ADD_DEPENDABOT="$2"; shift 2 ;;
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
case "$ADD_DEPENDABOT" in
    auto|always|never) ;;
    *) die "--add-dependabot takes 'auto', 'always' or 'never', got '$ADD_DEPENDABOT'" ;;
esac

command -v git    &>/dev/null || die "git not found in PATH"
command -v pinact &>/dev/null || die "pinact not found - see https://github.com/suzuki-shunsuke/pinact#install"
command -v uv     &>/dev/null || die "uv not found - see https://docs.astral.sh/uv/getting-started/installation/"
command -v gh     &>/dev/null || die "gh not found - install GitHub CLI"
gh auth status &>/dev/null || die "gh is not authenticated - run 'gh auth login'"
# pinact needs GITHUB_TOKEN to avoid rate limits
if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    if [[ -n "${GH_TOKEN:-}" ]]; then
        export GITHUB_TOKEN="$GH_TOKEN"
    elif token="$(gh auth token 2>/dev/null)" && [[ -n "$token" ]]; then
        export GITHUB_TOKEN="$token"
    else
        warn "GITHUB_TOKEN is not set - pinact may hit GitHub API rate limits."
    fi
fi

# Latest version of our actions
latest_release="$(gh api "repos/$SHARED_ACTIONS/releases/latest" --jq .tag_name)" \
    || die "Could not look up the latest release of $SHARED_ACTIONS"
SHARED_MAJOR="${latest_release%%.*}"
[[ "$SHARED_MAJOR" =~ ^v[0-9]+$ ]] \
    || die "Unexpected latest release tag for $SHARED_ACTIONS: '$latest_release'"

BRANCH="pin-actions-to-sha"
PR_TITLE="Update GitHub Actions references to follow our pinning policy"
COMMIT_MSG="$PR_TITLE"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HELPER="$SCRIPT_DIR/../python/pin_actions_helper.py"
[[ -f "$HELPER" ]] || die "Python helper not found: $HELPER"

mkdir -p "$WORK_DIR"
SUMMARY=()
FAILED=()

# `set -e` is off inside process_repo, so each step reports failures here
fail() {
    warn "$2 - skipping $1."
    FAILED+=("$1: $2")
}

# Skip our own actions, and pin @release/v1 branches to the latest release
PINACT_ARGS=(--log-level warn --exclude "(?i)^${SHARED_ACTIONS}/" --branch-to-tag '^release/v1$')

run_pinact() {
    local repo_dir="$1"; shift
    local code=0
    (cd "$repo_dir" && pinact run "${PINACT_ARGS[@]}" "$@" >&2) || code=$?
    [[ $code -eq 0 || $code -eq 2 ]] || return "$code"
}

# References that could not be pinned by pinact
unpinned_refs() {
    local repo_dir="$1"; shift
    local code=0 out
    out="$(cd "$repo_dir" && pinact run --fix=false --no-api "${PINACT_ARGS[@]}" "$@" 2>&1)" || code=$?
    [[ $code -eq 0 || $code -eq 2 ]] || { echo "$out" >&2; return "$code"; }
    grep -v "failed to handle a line" <<< "$out" || true
}

extra_files() {
    git -C "$1" grep -lE 'uses:[[:space:]]*["'\'']?[A-Za-z0-9_.-]+/[^[:space:]]+@' \
        -- '*.yml' '*.yaml' '*.md' \
        ':!.github/workflows/' ':!action.yml' ':!action.yaml' \
        ':!**/action.yml' ':!**/action.yaml' 2>/dev/null || true
}

cleanup_branch() {
    local repo_dir="$1" base="$2"
    git -C "$repo_dir" checkout -f "$base" --quiet 2>/dev/null || true
    git -C "$repo_dir" branch -D "$BRANCH" --quiet 2>/dev/null || true
}

# Uses the variables set in process_repo
pr_body() {
    echo "Make the GitHub Actions references in this repository follow our pinning policy (see neuroinformatics-unit/scripts#23): third-party actions are pinned to commit SHAs, so that a moved or compromised tag can't change what runs in our CI, and our own actions (\`${SHARED_ACTIONS}\`) are referenced by their latest major version tag, so that fixes reach every repository without a PR."
    echo
    if [[ "$pinned" == true ]]; then
        echo "- Pins third-party actions to full commit SHAs, with the version as a trailing comment (e.g. \`# v7.0.1\`). Every pin is the commit the existing tag already pointed to, so no versions are upgraded."
    fi
    if [[ "$branch_pinned" == true ]]; then
        echo "- Pins \`pypa/gh-action-pypi-publish@release/v1\` to its latest release, as a branch has no fixed commit."
    fi
    if [[ "$bumped" == true ]]; then
        echo "- Moves our own actions to \`@${SHARED_MAJOR}\`, from an older version, \`@main\` or a SHA. See the [release notes](https://github.com/${SHARED_ACTIONS}/releases) for what changed between major versions."
    fi
    if [[ "$dependabot_added" == true ]]; then
        echo "- ${dependabot}"
    fi
    echo
    echo "This PR was opened by a script from neuroinformatics-unit/scripts#23, written by @Aniketsy."
    if [[ -n "$ISSUE" ]]; then
        echo
        echo "Tracked in ${ISSUE}"
    fi
    echo
    echo "### Before merging"
    echo "- [ ] Check that CI passes"
    if [[ "$bumped" == true ]]; then
        echo "- [ ] Check the jobs that CI does not run on a PR (e.g. releases and deployments), as they also moved to \`@${SHARED_MAJOR}\`"
    fi
    if [[ -n "$not_bumped" ]]; then
        echo "- [ ] Replace the references to our actions that do not exist in \`${SHARED_MAJOR}\` (listed below)"
    fi
    if [[ -n "$leftovers" ]]; then
        echo "- [ ] Pin the references that could not be pinned automatically, or keep them deliberately (listed below)"
    fi
    if [[ -n "$notes" ]]; then
        echo "${notes%$'\n'}"
    fi
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
    local helper_args=(--major "$SHARED_MAJOR") not_bumped
    [[ "$WORKFLOWS_ONLY" == true ]] && helper_args+=(--workflows-only)
    if ! not_bumped="$(uv run --quiet "$HELPER" bump-shared "$repo_dir" "${helper_args[@]}")"; then
        fail "$repo" "Updating $SHARED_ACTIONS references failed"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    # What changed, for the PR body
    local bumped=false pinned=false branch_pinned=false dependabot_added=false
    local diff_after_bump
    diff_after_bump="$(git -C "$repo_dir" diff)"
    [[ -n "$diff_after_bump" ]] && bumped=true
    local extras=() f
    if [[ "$WORKFLOWS_ONLY" != true ]]; then
        while IFS= read -r f; do extras+=("$f"); done < <(extra_files "$repo_dir")
    fi
    if ! run_pinact "$repo_dir"; then
        fail "$repo" "pinact failed (GitHub API error?)"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if [[ ${#extras[@]} -gt 0 ]] && ! run_pinact "$repo_dir" "${extras[@]}"; then
        fail "$repo" "pinact failed on docs/example files"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi

    local diff_after_pin
    diff_after_pin="$(git -C "$repo_dir" diff)"
    [[ "$diff_after_pin" != "$diff_after_bump" ]] && pinned=true
    grep -qE '^-.*uses:.*@release/v1' <<< "$diff_after_pin" && branch_pinned=true

    #4. Collect notes for the reviewer
    local leftovers more dependabot notes=""
    local had_dependabot=false
    [[ -e "$repo_dir/.github/dependabot.yml" || -e "$repo_dir/.github/dependabot.yaml" ]] && had_dependabot=true
    if ! leftovers="$(unpinned_refs "$repo_dir")"; then
        fail "$repo" "pinact check failed"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if [[ ${#extras[@]} -gt 0 ]]; then
        if ! more="$(unpinned_refs "$repo_dir" "${extras[@]}")"; then
            fail "$repo" "pinact check failed on docs/example files"
            cleanup_branch "$repo_dir" "$base"
            return 0
        fi
        [[ -n "$more" ]] && leftovers+="${leftovers:+$'\n'}$more"
    fi
    if ! dependabot="$(uv run --quiet "$HELPER" dependabot "$repo_dir" --add "$ADD_DEPENDABOT")"; then
        fail "$repo" "Dependabot check failed"
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if [[ "$had_dependabot" != true && -e "$repo_dir/.github/dependabot.yml" ]]; then
        dependabot_added=true
        if ! git -C "$repo_dir" add --intent-to-add -- .github/dependabot.yml; then
            fail "$repo" "Could not add the new Dependabot config"
            cleanup_branch "$repo_dir" "$base"
            return 0
        fi
    fi

    if [[ -n "$not_bumped" ]]; then
        warn "$SHARED_ACTIONS references not moved to $SHARED_MAJOR in $repo:"
        echo "$not_bumped" >&2
        notes+="
These actions do not exist in \`${SHARED_MAJOR}\`, so the references were left alone:
\`\`\`
${not_bumped}
\`\`\`
"
    fi
    if [[ -n "$leftovers" ]]; then
        warn "Third-party references not pinned in $repo:"
        echo "$leftovers" >&2
        notes+="
These references could not be pinned automatically (e.g. branch references such as \`@main\`):
\`\`\`
${leftovers}
\`\`\`
"
    fi
    if [[ "$dependabot_added" == true ]]; then
        log "$dependabot"
    elif [[ -n "$dependabot" ]]; then
        warn "Dependabot in $repo:"
        echo "$dependabot" >&2
        notes+="
${dependabot}
"
    fi

    if git -C "$repo_dir" diff --quiet; then
        log "Nothing to change in $repo - skipping PR."
        if [[ -n "$notes" ]]; then
            warn "No PR for $repo, so the warnings above are not tracked anywhere else."
            SUMMARY+=("$repo: nothing to change, but see its warnings in the log (no PR to track them)")
        fi
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi

    log "Diff preview:"
    git -C "$repo_dir" --no-pager diff

    if [[ "$DRY_RUN" == true ]]; then
        log "[DRY RUN] Would commit, push, and open a PR against '$base' with this body:"
        pr_body
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
    body="$(pr_body)"

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

log "Updating actions in $ORG, with $SHARED_ACTIONS on @$SHARED_MAJOR (branch: $BRANCH, dry run: $DRY_RUN)"
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
