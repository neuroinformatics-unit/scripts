# /// script
# requires-python = ">=3.12"
# dependencies = ["pyyaml"]
# ///
"""Helper for bash/pin_actions_to_sha.sh."""

import argparse
import re
import subprocess
import sys
from functools import cache
from pathlib import Path

import yaml

SHARED = "neuroinformatics-unit/actions"
SHARED_RE = re.compile(
    r"(?P<head>uses:\s*[\"']?" + re.escape(SHARED) + r"/(?P<path>[\w./-]+)@)"
    # The ref ends at a letter or digit, so "@v2." keeps its full stop
    r"(?P<ref>[\w./-]*\w)(?P<quote>[\"']?)(?P<comment>[ \t]*#[^\r\n]*)?",
    re.IGNORECASE,
)
# A comment that only holds a version, e.g. "# v3.0.0"
VERSION_COMMENT_RE = re.compile(r"\s*#\s*v?\d[\w.-]*\s*")
# Actions that upload to PyPI
PYPI_RE = re.compile(
    r"^[^#\n]*uses:\s*[\"']?(?:pypa/gh-action-pypi-publish|"
    + re.escape(SHARED)
    + r"/upload_pypi)@",
    re.IGNORECASE | re.MULTILINE,
)

DEPENDABOT_FILE = ".github/dependabot.yml"
DEPENDABOT_ENTRY = """\
  - package-ecosystem: "github-actions"
    directories:
{directories}
    schedule:
      interval: "monthly"
    cooldown:
      default-days: 7
    groups:
      github-actions:
        patterns: ["*"]
"""


def tracked_files(repo: Path) -> list[Path]:
    out = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "-z"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    ).stdout
    return [Path(f) for f in out.split("\0") if f]


def is_workflow(path: Path) -> bool:
    return path.parent.as_posix() == ".github/workflows" and path.suffix in (
        ".yml",
        ".yaml",
    )


def is_action(path: Path) -> bool:
    return path.name in ("action.yml", "action.yaml")


def read_text(path: Path) -> str | None:
    """Read a file without changing its line endings."""
    if path.is_symlink() or not path.is_file():
        return None
    try:
        return path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return None


@cache
def exists_in_shared(path: str, ref: str) -> bool:
    """Check that an action (or reusable workflow) exists at `ref`."""
    if path.endswith((".yml", ".yaml")):
        candidates = [path]
    else:
        candidates = [f"{path}/action.yml", f"{path}/action.yaml"]
    for candidate in candidates:
        result = subprocess.run(
            ["gh", "api", f"repos/{SHARED}/contents/{candidate}?ref={ref}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        if "(HTTP 404)" not in result.stderr:
            sys.exit(f"gh api failed for {candidate}@{ref}: {result.stderr.strip()}")
    return False


def bump_shared_actions(text: str, major: str) -> tuple[str, list[str]]:
    """Move shared-action refs to `major`; return new text and refs left alone."""
    skipped = []

    def repl(m: re.Match) -> str:
        line_start = text.rfind("\n", 0, m.start()) + 1
        commented_out = text[line_start : m.start()].lstrip().startswith("#")
        if m["ref"] == major or commented_out:
            return m[0]
        path = m["path"].strip("/")
        if not exists_in_shared(path, major):
            line = text.count("\n", 0, m.start()) + 1
            skipped.append(
                f"{line}: {SHARED}/{path}@{m['ref']} (does not exist in {major})"
            )
            return m[0]
        comment = m["comment"] or ""
        if VERSION_COMMENT_RE.fullmatch(comment):
            comment = ""
        return m["head"] + major + m["quote"] + comment

    return SHARED_RE.sub(repl, text), skipped


def cmd_bump_shared(args: argparse.Namespace) -> None:
    if not re.fullmatch(r"v\d+", args.major):
        sys.exit(f"--major must look like 'v3', got '{args.major}'")
    for rel in tracked_files(args.repo):
        if not (is_workflow(rel) or is_action(rel)):
            if args.workflows_only or rel.suffix not in (".yml", ".yaml", ".md"):
                continue
        path = args.repo / rel
        text = read_text(path)
        if text is None:
            continue
        new_text, skipped = bump_shared_actions(text, args.major)
        if new_text != text:
            path.write_bytes(new_text.encode("utf-8"))
        for ref in skipped:
            print(f"{rel.as_posix()}:{ref}")


def action_dirs(files: list[Path]) -> list[str]:
    """Return the directories ("/", "/lint", ...) that hold actions."""
    dirs = set()
    for path in files:
        if is_workflow(path):
            dirs.add("/")
        elif is_action(path):
            parent = path.parent.as_posix()
            dirs.add("/" if parent == "." else f"/{parent}")
    return sorted(dirs)


def publishes_to_pypi(repo: Path, files: list[Path]) -> bool:
    for rel in files:
        if is_workflow(rel) or is_action(rel):
            text = read_text(repo / rel)
            if text and PYPI_RE.search(text):
                return True
    return False


def covered_patterns(config: object) -> list[str]:
    """Return the directories Dependabot checks for actions."""
    updates = config.get("updates") if isinstance(config, dict) else None
    patterns = []
    for update in updates if isinstance(updates, list) else []:
        if (
            not isinstance(update, dict)
            or update.get("package-ecosystem") != "github-actions"
        ):
            continue
        if "directory" in update:
            patterns.append(str(update["directory"]))
        directories = update.get("directories")
        if isinstance(directories, list):
            patterns.extend(str(d) for d in directories)
    # Leading slash, no trailing slash
    return ["/" + p.strip("/") if p.strip("/") else "/" for p in patterns]


def is_covered(directory: str, pattern: str) -> bool:
    """Check a directory against a Dependabot pattern.

    `*` matches one path segment, `**` matches any number.
    """
    regex = ""
    for part in re.split(r"(\*\*/?|\*)", pattern):
        if part.startswith("**"):
            regex += ".*"
        elif part == "*":
            regex += "[^/]*"
        else:
            regex += re.escape(part)
    return re.fullmatch(regex, directory) is not None


def dependabot_entry(dirs: list[str]) -> str:
    directories = "\n".join(f'      - "{d}"' for d in dirs)
    return DEPENDABOT_ENTRY.format(directories=directories)


def fenced(text: str) -> str:
    return f"```yaml\n{text}```"


def cmd_dependabot(args: argparse.Namespace) -> None:
    repo = args.repo
    files = tracked_files(repo)
    needed = action_dirs(files)
    if not needed:
        return
    entry = dependabot_entry(needed)

    config_file = next(
        (
            p
            for p in (repo / DEPENDABOT_FILE, repo / ".github" / "dependabot.yaml")
            if p.is_file()
        ),
        None,
    )
    if config_file is None:
        config = f"version: 2\nupdates:\n{entry}"
        pypi = publishes_to_pypi(repo, files)
        website = repo.resolve().name.lower().endswith(".github.io")
        if args.add == "always" or (args.add == "auto" and (pypi or website)):
            target = repo / DEPENDABOT_FILE
            target.parent.mkdir(exist_ok=True)
            target.write_bytes(config.encode("utf-8"))
            if pypi:
                reason = (
                    "this repository publishes to PyPI, so an outdated or "
                    "compromised action here would affect our users"
                )
            elif website:
                reason = "this is the organisation's website, and its CI runs often"
            else:
                reason = "requested when running the script"
            print(
                f"Adds `{DEPENDABOT_FILE}` ({reason}). Dependabot will open "
                "one grouped PR a month for GitHub Actions updates, and only "
                "propose releases that are at least a week old."
            )
        else:
            print(
                "This repository has no Dependabot config, so its actions "
                "will not get update PRs. Whether that is worth the extra "
                "PRs is up to the maintainers; if you want it, add this as "
                f"`{DEPENDABOT_FILE}` (one grouped PR a month):\n"
                f"{fenced(config)}"
            )
        return

    try:
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as err:
        print(f"Could not parse `.github/{config_file.name}`: {err}")
        return

    patterns = covered_patterns(config)
    missing = [d for d in needed if not any(is_covered(d, p) for p in patterns)]
    if not missing:
        return
    where = ", ".join(f"`{d}`" for d in missing)
    note = (
        f"`.github/{config_file.name}` has no `github-actions` entry "
        f"covering {where}, so actions there will not get update PRs. "
    )
    if patterns:
        note += "Add them to the directories of the existing entry."
    else:
        note += (
            "An entry like this under `updates:` would cover them:\n"
            f"{fenced(dependabot_entry(missing))}"
        )
    print(note)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(required=True)

    bump = commands.add_parser("bump-shared")
    bump.add_argument("repo", type=Path)
    bump.add_argument("--major", required=True)
    bump.add_argument("--workflows-only", action="store_true")
    bump.set_defaults(func=cmd_bump_shared)

    dependabot = commands.add_parser("dependabot")
    dependabot.add_argument("repo", type=Path)
    dependabot.add_argument(
        "--add", choices=("auto", "always", "never"), default="auto"
    )
    dependabot.set_defaults(func=cmd_dependabot)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
