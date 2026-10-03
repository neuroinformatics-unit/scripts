#!/usr/bin/env python3

import re
import sys
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap, CommentedSeq


yaml = YAML()
yaml.preserve_quotes = True
yaml.width = 4096
yaml.indent(mapping=4, sequence=4, offset=2)


REVS = {
    "https://github.com/pre-commit/pre-commit-hooks": "v6.0.0",
    "https://github.com/astral-sh/ruff-pre-commit": "v0.16.6",
    "https://github.com/pre-commit/mirrors-mypy": "v1.13.0",
    "https://github.com/mgedmin/check-manifest": "0.50",
    "https://github.com/codespell-project/codespell": "v2.4.3",
}

BLACK_REPO = "https://github.com/psf/black-pre-commit-mirror"
RUFF_REPO = "https://github.com/astral-sh/ruff-pre-commit"
RUFF_ARGS = ["--config=pyproject.toml"]


def make_hook(repo, rev, hook_id, args=None, additional_dependencies=None):
    entry = CommentedMap()
    entry["repo"] = repo
    entry["rev"] = rev

    hook = CommentedMap()
    hook["id"] = hook_id

    if args:
        hook["args"] = CommentedSeq(args)

    if additional_dependencies:
        hook["additional_dependencies"] = CommentedSeq(
            additional_dependencies
        )

    entry["hooks"] = CommentedSeq([hook])

    return entry


STANDARD_REPOS = {
    "https://github.com/pre-commit/mirrors-mypy": make_hook(
        "https://github.com/pre-commit/mirrors-mypy",
        "v1.13.0",
        "mypy",
        additional_dependencies=["types-setuptools"],
    ),
    "https://github.com/mgedmin/check-manifest": make_hook(
        "https://github.com/mgedmin/check-manifest",
        "0.50",
        "check-manifest",
        args=["--no-build-isolation"],
        additional_dependencies=[
            "setuptools>=77",
            "wheel",
            "setuptools-scm[toml]>=8",
        ],
    ),
    "https://github.com/codespell-project/codespell": make_hook(
        "https://github.com/codespell-project/codespell",
        "v2.4.3",
        "codespell",
        additional_dependencies=["tomli"],
    ),
}


def fix_ruff_hooks(entry):
    hooks = entry["hooks"]
    ids = {hook["id"] for hook in hooks}

    for hook in hooks:
        if hook["id"] == "ruff":
            hook["args"] = list(RUFF_ARGS)

    if "ruff-format" not in ids:
        fmt = CommentedMap()
        fmt["id"] = "ruff-format"
        fmt["args"] = list(RUFF_ARGS)
        hooks.append(fmt)


def standardize_precommit(path):
    with open(path) as f:
        data = yaml.load(f)

    existing_repos = set()
    new_repos = []

    for entry in data["repos"]:
        url = entry["repo"]

        if url == BLACK_REPO:
            continue

        existing_repos.add(url)

        if url in REVS:
            entry["rev"] = REVS[url]

        if url == RUFF_REPO:
            fix_ruff_hooks(entry)

        new_repos.append(entry)

    # add any missing standard hooks
    for repo, entry in STANDARD_REPOS.items():
        if repo not in existing_repos:
            new_repos.append(entry)

    data["repos"] = new_repos

    with open(path, "w") as f:
        yaml.dump(data, f)


def standardize_pyproject(path):
    text = path.read_text()

    text = re.sub(
        r"(?ms)^\[tool\.black\]\s*\n.*?(?=^\[|\Z)",
        "",
        text,
    )

    text = re.sub(
        r'(?m)^\s*"black",\s*\n',
        "",
        text,
    )

    # add the standard codespell configuration if it doesn't exist
    if not re.search(r"(?m)^\[tool\.codespell\]\s*$", text):
        text = text.rstrip() + """

[tool.codespell]
skip = '.git'
check-hidden = true
"""

    path.write_text(text)


def standardize(path):
    precommit_path = Path(path)
    pyproject_path = precommit_path.parent / "pyproject.toml"

    standardize_precommit(precommit_path)

    if pyproject_path.exists():
        standardize_pyproject(pyproject_path)
        print(f"updated {precommit_path} and {pyproject_path}")
    else:
        print(
            f"updated {precommit_path}; "
            f"no pyproject.toml found, skipping"
        )


path = sys.argv[1] if len(sys.argv) > 1 else ".pre-commit-config.yaml"
standardize(path)
