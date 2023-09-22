"""A rough script to star all our repos, because they are awesome (and there are many of them!)
"""
import requests
import subprocess

org_names = ['brainglobe', 'neuroinformatics-unit'] # add/remove other orgs you'd like to star here


for org_name in org_names:
    # Get a list of repositories in the organization
    org_repos_url = f'https://api.github.com/orgs/{org_name}/repos'
    headers = {
        'Accept': 'application/vnd.github.v3+json'
    }

    response = requests.get(org_repos_url, headers=headers)
    if response.status_code == 200:
        repos = response.json()
        # Star each repository in the organization
        for repo in repos:
            subprocess.run(['gh', 'api' ,'--method', 'PUT', '-H', 'Accept: application/vnd.github+json', '-H', 'X-GitHub-Api-Version: 2022-11-28', f'/user/starred/{org_name}/{repo["name"]}'])