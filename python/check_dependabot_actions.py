"""Report GitHub Actions files that Dependabot does not keep up to date."""

import re
import subprocess
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    sys.exit("PyYAML is required: pip install pyyaml")


def action_dirs(repo: Path) -> list[str]:
    """Return the directories ("/", "/lint", ...) that hold actions."""
    files = subprocess.run(
        ["git", "-C", str(repo), "ls-files"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    dirs = set()
    for f in files:
        path = Path(f)
        if path.parent.as_posix() == ".github/workflows" and path.suffix in (
            ".yml",
            ".yaml",
        ):
            dirs.add("/")
        elif path.name in ("action.yml", "action.yaml"):
            parent = path.parent.as_posix()
            dirs.add("/" if parent == "." else f"/{parent}")
    return sorted(dirs)


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


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    repo = Path(sys.argv[1])

    needed = action_dirs(repo)
    if not needed:
        return

    config_file = next(
        (
            p
            for p in (
                repo / ".github" / "dependabot.yml",
                repo / ".github" / "dependabot.yaml",
            )
            if p.is_file()
        ),
        None,
    )
    if config_file is None:
        print("No .github/dependabot.yml: pinned SHAs will not be updated")
        return

    try:
        config = yaml.safe_load(config_file.read_text(encoding="utf-8"))
    except (yaml.YAMLError, UnicodeDecodeError) as err:
        print(f"Could not parse {config_file.name}: {err}")
        return

    patterns = covered_patterns(config)
    if not patterns:
        print(f"{config_file.name} has no 'github-actions' entry")
        return

    for d in needed:
        if not any(is_covered(d, p) for p in patterns):
            print(f"{config_file.name} has no 'github-actions' entry for {d}")


if __name__ == "__main__":
    main()
