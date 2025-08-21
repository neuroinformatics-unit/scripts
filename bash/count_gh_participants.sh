#!/usr/bin/env bash
set -euo pipefail

# Count unique community participants (issue/PR openers + commenters)
# Requires: GitHub CLI (`gh`) and `jq` available in PATH.
# Usage:
#   ./count_participants.sh <owner> [repo]
# Examples:
#   ./count_participants.sh neuroinformatics-unit
#   ./count_participants.sh neuroinformatics-unit movement

if ! command -v gh >/dev/null 2>&1; then
  echo "Error: GitHub CLI 'gh' is required." >&2
  exit 1
fi

OWNER="${1:-}"
REPO="${2:-}"

if [[ -z "$OWNER" ]]; then
  echo "Usage: $0 <owner> [repo]" >&2
  exit 1
fi

tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

fetch_repo_participants() {
  local owner="$1"
  local repo="$2"

  # Issue commenters
  gh api "repos/${owner}/${repo}/issues/comments" --paginate --jq '.[].user.login' 2>/dev/null || true
  # PR commenters/reviewers (review comments)
  gh api "repos/${owner}/${repo}/pulls/comments"  --paginate --jq '.[].user.login' 2>/dev/null || true
  # Issue openers (includes PRs as issues too, but we dedupe later)
  gh api "repos/${owner}/${repo}/issues"          --paginate --jq '.[].user.login' 2>/dev/null || true
  # PR openers
  gh api "repos/${owner}/${repo}/pulls"           --paginate --jq '.[].user.login' 2>/dev/null || true
}

if [[ -n "$REPO" ]]; then
  # Single repo mode
  fetch_repo_participants "$OWNER" "$REPO" \
    | grep -v '^null$' \
    | sort -u > "$tmpdir/all_participants.txt"
else
  # Owner-wide mode: get all repos for an org or a user
  repos_file="$tmpdir/repos.txt"
  # Try orgs first; if that fails, try users.
  if ! gh api "orgs/${OWNER}/repos?per_page=100" --paginate --jq '.[].name' > "$repos_file" 2>/dev/null; then
    gh api "users/${OWNER}/repos?per_page=100" --paginate --jq '.[].name' > "$repos_file"
  fi

  : > "$tmpdir/all_participants.txt"
  while IFS= read -r repo; do
    fetch_repo_participants "$OWNER" "$repo" >> "$tmpdir/all_participants.txt" || true
  done < "$repos_file"

  # Remove possible nulls, dedupe
  grep -v '^null$' "$tmpdir/all_participants.txt" | sort -u -o "$tmpdir/all_participants.txt"
fi

count="$(wc -l < "$tmpdir/all_participants.txt" | tr -d '[:space:]')"
echo "$count"
