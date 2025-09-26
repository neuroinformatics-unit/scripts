import os
import requests
import subprocess
from pathlib import Path

from tqdm import tqdm

BACKUP_FOLDER = Path("/Users/nsirmpilatze/Code/BackUp")
ORG = "neuroinformatics-unit"
TOKEN = os.getenv('GH_PAT')
if not TOKEN:
    TOKEN = input('Enter your GitHub Personal Access Token: ')

url = f"https://api.github.com/orgs/{ORG}/repos?per_page=100&type=all"

BACKUP_FOLDER.mkdir(parents=True, exist_ok=True)

errors = []

while url:

    response = requests.get(url, headers={"Authorization": f"token {TOKEN}"})
    response.raise_for_status()
    n_repos = len(response.json())

    for repo in tqdm(response.json(), total=n_repos):

        ssh = repo["ssh_url"]
        name = repo["name"]
        repo_dir = BACKUP_FOLDER / f"{repo['name']}.git"

        if not repo_dir.is_dir():
            result = subprocess.run(["git", "clone", "--mirror", ssh, repo_dir.as_posix()], capture_output=True, text=True)

            if result.returncode != 0:
                errors.append(f"[ERROR] Failed to clone {repo['name']}: {result.stderr}")

        else:
            result = subprocess.run(["git", "-C", repo_dir.as_posix(), "fetch", "--all", "--prune"], capture_output=True, text=True)

            if result.returncode != 0:
                errors.append(f"[ERROR] Failed to fetch {repo['name']}: {result.stderr}")

    url = response.links.get("next", {}).get("url")

if any(errors):
    raise RuntimeError("Errors were encountered when backing up repositories:\n" + "\n".join(errors))
