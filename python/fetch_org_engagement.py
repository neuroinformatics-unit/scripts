#!/usr/bin/env python3
"""
Fetch all pull requests, commits, issues, and issue comments from a GitHub organization.

Auth: set env var GITHUB_TOKEN to a Personal Access Token with repo/read:org scopes.

Usage:
    python fetch_org_engagement.py --org <org_name> --out <output.json>
"""

import argparse
import os
import sys
import requests
import json

API_BASE = "https://api.github.com"

def get_headers(token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "basic-org-engagement-fetcher/1.0"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers

def get_paginated(url, headers, params=None):
    params = params or {}
    params["per_page"] = 100
    while url:
        resp = requests.get(url, headers=headers, params=params)
        if not resp.ok:
            print(f"Error fetching {url}: {resp.status_code} {resp.text}", file=sys.stderr)
            break
        data = resp.json()
        yield from data if isinstance(data, list) else []
        # Pagination
        link = resp.headers.get("Link")
        url = None
        if link:
            for part in link.split(","):
                if 'rel="next"' in part:
                    url = part[part.find("<")+1:part.find(">")]
                    break

def list_org_repos(org, headers):
    url = f"{API_BASE}/orgs/{org}/repos"
    return [r for r in get_paginated(url, headers) if not r.get("fork")]

def fetch_issues(owner, repo, headers):
    url = f"{API_BASE}/repos/{owner}/{repo}/issues"
    for issue in get_paginated(url, headers, params={"state": "all"}):
        if issue.get("pull_request"):
            continue
        yield {
            "type": "issue",
            "repo": f"{owner}/{repo}",
            "id": issue.get("id"),
            "actor": issue.get("user", {}).get("login"),
            "created_at": issue.get("created_at"),
            "url": issue.get("html_url"),
            "title": issue.get("title"),
        }

def fetch_issue_comments(owner, repo, headers):
    url = f"{API_BASE}/repos/{owner}/{repo}/issues/comments"
    for comment in get_paginated(url, headers):
        yield {
            "type": "issue_comment",
            "repo": f"{owner}/{repo}",
            "id": comment.get("id"),
            "actor": comment.get("user", {}).get("login"),
            "created_at": comment.get("created_at"),
            "url": comment.get("html_url"),
            "issue_url": comment.get("issue_url"),
        }

def fetch_pull_requests(owner, repo, headers):
    url = f"{API_BASE}/repos/{owner}/{repo}/pulls"
    for pr in get_paginated(url, headers, params={"state": "all"}):
        yield {
            "type": "pull_request",
            "repo": f"{owner}/{repo}",
            "id": pr.get("id"),
            "actor": pr.get("user", {}).get("login"),
            "created_at": pr.get("created_at"),
            "url": pr.get("html_url"),
            "title": pr.get("title"),
        }

def fetch_commits(owner, repo, headers):
    url = f"{API_BASE}/repos/{owner}/{repo}/commits"
    for commit in get_paginated(url, headers):
        commit_obj = commit.get("commit", {})
        yield {
            "type": "commit",
            "repo": f"{owner}/{repo}",
            "id": commit.get("sha"),
            "actor": (commit.get("author") or {}).get("login"),
            "created_at": (commit_obj.get("author") or {}).get("date"),
            "url": commit.get("html_url"),
            "message": commit_obj.get("message"),
        }

def main():
    parser = argparse.ArgumentParser(description="Fetch basic GitHub org engagements")
    parser.add_argument("--org", required=True, help="GitHub organization name")
    parser.add_argument("--out", default="org_engagements.json", help="Output JSON file")
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Warning: GITHUB_TOKEN not set. You may hit rate limits.", file=sys.stderr)
    headers = get_headers(token)

    print(f"Listing repositories for org: {args.org}...", file=sys.stderr)
    repos = list_org_repos(args.org, headers)
    print(f"Found {len(repos)} repositories.", file=sys.stderr)

    all_events = []
    for repo in repos:
        full_name = repo.get("full_name")
        owner, name = full_name.split("/", 1)
        print(f"Processing {full_name}...", file=sys.stderr)
        all_events.extend(fetch_issues(owner, name, headers))
        all_events.extend(fetch_issue_comments(owner, name, headers))
        all_events.extend(fetch_pull_requests(owner, name, headers))
        all_events.extend(fetch_commits(owner, name, headers))

    print(f"Writing {len(all_events)} events to {args.out}", file=sys.stderr)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(all_events, f, indent=2)

if __name__ == "__main__":
    main()
