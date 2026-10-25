#!/usr/bin/env bash
set -euo pipefail

ORG="neuroinformatics-unit"
REVIEWER=""
ISSUE=""
DRY_RUN=false
ONLY_REPO=""

WORK_DIR="$(pwd)/.remove_artifactci_work"

REPOS=(
"actions"
"datashuttle"
"ethology"
"movement"
"neuroinformatics-unit.github.io"
"sphinx-deployment-test"
)

usage() {
    echo "Usage: $0 [--dry-run] [--repo <name>] [--org <org>] [--reviewer <users>] [--issue <issue>]"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run)  DRY_RUN=true;    shift ;;
        --repo)     ONLY_REPO="$2";  shift 2 ;;
        --org)      ORG="$2";        shift 2 ;;
        --reviewer) REVIEWER="$2";   shift 2 ;;
        --issue)    ISSUE="$2";      shift 2 ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "Unknown argument: $1"; usage; exit 1 ;;
    esac
done

log()  { echo "[INFO]  $*"; }
warn() { echo "[WARN]  $*" >&2; }
die()  { echo "[ERROR] $*" >&2; exit 1; }

[[ "$ONLY_REPO" == *[,[:space:]]* ]] && die "--repo takes a single repository name, got '$ONLY_REPO'"

command -v git &>/dev/null || die "git not found in PATH"
command -v awk &>/dev/null || die "awk not found in PATH"
if [[ "$DRY_RUN" != true ]]; then
    command -v gh &>/dev/null || die "gh not found - install GitHub CLI"
    gh auth status &>/dev/null || die "gh is not authenticated - run 'gh auth login'"
fi

BRANCH="remove-artifactci"
PR_TITLE="Remove artifact.ci docs preview upload"
COMMIT_MSG="Remove artifact.ci docs preview upload"

mkdir -p "$WORK_DIR"

# Delete the artifact.ci steps, input, conditions and bullets from one file (md=1 for
# Markdown, nl=0 if the file has no final newline). A block is a line plus the lines
# below it that are blank or indented further.
AWK_PROG='
function indent(s)  { match(s, /^ */); return RLENGTH }
function blank(s)   { return s ~ /^[[:space:]]*$/ }
function is_item(s) { return s ~ /^ *[-*+] / }
function block_end(i,    j, ind, cont) {
    ind = indent(L[i]); cont = (md && is_item(L[i])); j = i + 1
    while (j <= n && (blank(L[j]) || indent(L[j]) > ind || \
                      (cont && !blank(L[j - 1]) && indent(L[j]) == ind && !is_item(L[j]) && L[j] !~ /^ *#/)))
        j++
    while (j - 1 > i && blank(L[j - 1])) j--
    return j - 1
}
function block_text(i,    e, k, t) {
    e = block_end(i); t = ""
    for (k = i; k <= e; k++) t = t L[k] "\n"
    return t
}
function delete_block(i,    e, k, prev) {
    e = block_end(i)
    for (k = i; k <= e; k++) del[k] = 1
    prev = i - 1
    while (prev >= 1 && del[prev]) prev--
    if (prev < 1 || blank(L[prev]))
        for (k = e + 1; k <= n && blank(L[k]); k++) del[k] = 1
    return e
}
{ L[NR] = $0 }
END {
    n = NR
    for (i = 1; i <= n; i++) {
        if (del[i]) continue
        if (L[i] ~ /^ *- /) {
            t = block_text(i)
            if (t ~ /uses: *["'"'"']?mmkal\/artifact\.ci/ || t ~ /steps\.artifactci-upload/) {
                i = delete_block(i); continue
            }
        }
        if (L[i] ~ /^ *use-artifactci:/)              { i = delete_block(i); continue }
        if (L[i] ~ /^ *if:.*inputs\.use-artifactci/)  { i = delete_block(i); continue }
        if (md && is_item(L[i]) && L[i] ~ /artifact\.ci|artifactci/) { i = delete_block(i); continue }
    }
    for (i = 1; i <= n; i++) {
        if (del[i] || L[i] !~ /^ *with: *$/) continue
        j = i + 1
        while (j <= n && (del[j] || blank(L[j]))) j++
        if (j > n || indent(L[j]) <= indent(L[i])) del[i] = 1
    }
    last = n
    while (last >= 1 && del[last]) last--
    if (!blank(L[n])) while (last >= 1 && blank(L[last])) { del[last] = 1; last-- }
    for (i = 1; i <= n; i++) if (!del[i]) { if (i == last && !nl) printf "%s", L[i]; else print L[i] }
}'

candidate_files() {
    git -C "$1" grep -lIiE 'artifactci|artifact\.ci' -- '*.yml' '*.yaml' '*.md' 2>/dev/null || true
}

leftover_mentions() {
    git -C "$1" grep -nIiE 'artifactci|artifact\.ci' 2>/dev/null || true
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

    # Fresh clone of the default branch
    rm -rf "$repo_dir"
    if [[ "$DRY_RUN" == true ]]; then
        git clone --quiet --depth=1 "https://github.com/$ORG/$repo.git" "$repo_dir"
    else
        gh repo clone "$ORG/$repo" "$repo_dir" -- --depth=1 --quiet
    fi || { warn "Clone failed for $repo - skipping."; return 0; }
    local base
    base="$(git -C "$repo_dir" symbolic-ref --short refs/remotes/origin/HEAD)"
    base="${base#origin/}"

    # Skip if the branch already exists
    if git -C "$repo_dir" ls-remote --exit-code --heads origin "$BRANCH" &>/dev/null; then
        warn "Branch '$BRANCH' already exists on remote - skipping $repo."
        return 0
    fi

    # Create branch and edit the files
    git -C "$repo_dir" checkout -b "$BRANCH" --quiet
    local files=() f md nl tmp
    while IFS= read -r f; do files+=("$f"); done < <(candidate_files "$repo_dir")
    if [[ ${#files[@]} -eq 0 ]]; then
        log "No mention of artifact.ci in $repo - skipping PR."
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    tmp="$(mktemp)"
    for f in "${files[@]}"; do
        md=0; [[ "$f" == *.md ]] && md=1
        nl=1; [[ -n "$(tail -c 1 "$repo_dir/$f")" ]] && nl=0
        awk -v md="$md" -v nl="$nl" "$AWK_PROG" "$repo_dir/$f" > "$tmp"
        cat "$tmp" > "$repo_dir/$f"
    done
    rm -f "$tmp"

    local leftovers review=""
    leftovers="$(leftover_mentions "$repo_dir")"
    if [[ -n "$leftovers" ]]; then
        warn "Mentions of artifact.ci left in $repo:"
        echo "$leftovers" >&2
        review="

### Please review
**Still mentioning artifact.ci** (not changed automatically; edit or remove by hand):
\`\`\`
${leftovers}
\`\`\`"
    fi

    if git -C "$repo_dir" diff --quiet; then
        log "Nothing to change in $repo - skipping PR."
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

    # Commit and push
    git -C "$repo_dir" add -u
    if git -C "$repo_dir" diff --cached --quiet; then
        warn "Nothing staged - skipping $repo."
        return 0
    fi
    if ! git -C "$repo_dir" commit --quiet -m "$COMMIT_MSG"; then
        warn "Commit failed for $repo - skipping."
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi
    if ! git -C "$repo_dir" push --quiet origin "$BRANCH"; then
        warn "Push failed for $repo (does the token have write access?) - skipping."
        cleanup_branch "$repo_dir" "$base"
        return 0
    fi

    # Open the PR
    local body
    body="Remove the artifact.ci docs preview.

\`build_sphinx_docs\` could upload the built docs with [artifact.ci](https://github.com/mmkal/artifact.ci) instead of \`actions/upload-artifact\` (\`use-artifactci: lazy\`) to get a preview link. artifact.ci has no tagged releases, so it is the one third-party action that cannot be pinned to a version like the others (see ${ORG}/actions#192). The docs are still uploaded with \`actions/upload-artifact\` as the \`docs-build\` artifact, so the deploy job is unaffected."
    if [[ "$repo" == "actions" ]]; then
        body+="

- Removes the \`use-artifactci\` input, the artifact.ci upload step and the preview URL summary step from \`build_sphinx_docs\`.
- Callers that still pass \`use-artifactci\` only get an \"Unexpected input(s)\" warning, so this can be merged before or after their PRs. Please publish a release afterwards so the \`@v3\` tag moves."
    else
        body+="

- Removes the \`use-artifactci\` input from the \`build_sphinx_docs\` call. This is safe to merge before or after the matching change in ${ORG}/actions."
    fi
    body+="

This PR was opened by a script. Please check that CI passes before merging.${review}"
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
    fi
}

log "Removing artifact.ci in $ORG (branch: $BRANCH, dry run: $DRY_RUN)"
if [[ -n "$ONLY_REPO" ]]; then
    process_repo "$ONLY_REPO" || warn "Unhandled error for $ONLY_REPO."
else
    for repo in "${REPOS[@]}"; do
        process_repo "$repo" || warn "Unhandled error for $repo - continuing."
        echo
    done
fi

log "Completed: $WORK_DIR"
