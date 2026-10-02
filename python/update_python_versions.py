#!/usr/bin/env python3
"""Update supported Python versions in a repo's pyproject.toml and CI workflows.

Called by bash/update_python_versions.sh.
Usage: update_python_versions.py <repo_dir> <min_minor> <max_minor> [review_file]
If review_file is given, remaining Python version mentions in the repo's tracked files
(after the updates, excluding lines this script manages) are written to it for review.
Exit codes: 0 = files changed, 2 = nothing to change, other = error.
"""

import fnmatch
import pathlib
import re
import subprocess
import sys

root = pathlib.Path(sys.argv[1])
lo, hi = int(sys.argv[2]), int(sys.argv[3])
minors = list(range(lo, hi + 1))
review_file = pathlib.Path(sys.argv[4]) if len(sys.argv) > 4 else None


def quote_of(text, default='"'):
    m = re.search(r"[\"']", text)
    return m.group(0) if m else default


def update_pyproject(text):
    # requires-python = ">=3.11" / ">=3.11.0" -> bump the minor version only
    def requires(m):
        return m.group(1) + str(lo) if int(m.group(2)) < lo else m.group(0)

    text = re.sub(r"(requires-python\s*=\s*[\"']\s*>=\s*3\.)(\d+)", requires, text)

    # A contiguous block of "Programming Language :: Python :: 3.X" classifiers
    def classifiers(m):
        indent, q = re.match(r"([ \t]*)([\"'])", m.group(0)).groups()
        return "".join(
            f"{indent}{q}Programming Language :: Python :: 3.{v}{q},\n" for v in minors
        )

    text = re.sub(
        r"(?:^[ \t]*([\"'])Programming Language :: Python :: 3\.\d+\1,?[ \t]*\n)+",
        classifiers,
        text,
        flags=re.M,
    )

    # [tool.black] target-version = ['py311', 'py312', 'py313']
    def black_targets(m):
        q = quote_of(m.group(2), "'")
        return m.group(1) + ", ".join(f"{q}py3{v}{q}" for v in minors) + m.group(3)

    text = re.sub(
        r"(target-version\s*=\s*\[)([^\]]*py3\d+[^\]]*)(\])", black_targets, text
    )

    # [tool.ruff] target-version = "py311"
    def ruff_target(m):
        return f"{m.group(1)}{m.group(2)}py3{lo}{m.group(2)}" if int(m.group(3)) < lo else m.group(0)

    text = re.sub(r"(target-version\s*=\s*)([\"'])py3(\d+)\2", ruff_target, text)

    # legacy tox: envlist = py{311,312,313}
    text = re.sub(
        r"(envlist\s*=\s*py\{)3\d+(?:\s*,\s*3\d+)*(\})",
        lambda m: m.group(1) + ",".join(f"3{v}" for v in minors) + m.group(2),
        text,
    )

    # legacy tox [gh-actions] mapping: "3.11: py311" lines
    def gh_actions(m):
        indent = re.match(r"[ \t]*", m.group(0)).group(0)
        return "".join(f"{indent}3.{v}: py3{v}\n" for v in minors)

    text = re.sub(
        r"(?:^[ \t]*3\.\d+\s*:\s*py3\d+[ \t]*\n)+", gh_actions, text, flags=re.M
    )
    return text


LIST_RE = re.compile(r"^(\s*python-version:\s*\[)(\s*)([^\]]*?)(\s*)(\].*)$")
SINGLE_RE = re.compile(r"^(\s*(?:-\s*)?python-version:\s*)([\"']?)3\.(\d+)\2(\s*(?:#.*)?)$")


def update_matrix_block(block):
    """Update one `matrix:` block (list of lines without newlines).

    Returns the block and whether it held a multi-version python matrix.
    """
    old_max = None
    for i, line in enumerate(block):
        m = LIST_RE.match(line)
        if not m:
            continue
        found = [int(v) for v in re.findall(r"3\.(\d+)", m.group(3))]
        if len(found) < 2:
            continue  # single-version matrix (e.g. benchmarks) - leave alone
        old_max = max(found)
        q = quote_of(m.group(3))
        new_list = ", ".join(f"{q}3.{v}{q}" for v in minors)
        block[i] = m.group(1) + m.group(2) + new_list + m.group(4) + m.group(5)

    if old_max is None:
        return block, False

    for i, line in enumerate(block):
        m = SINGLE_RE.match(line)
        if m and (int(m.group(3)) == old_max or int(m.group(3)) < lo):
            block[i] = f"{m.group(1)}{m.group(2)}3.{hi}{m.group(2)}{m.group(4)}"
    return block, True


def update_workflow(text, in_matrix=None):
    """Update multi-version matrices; mark their lines in `in_matrix` if given."""
    lines = text.split("\n")
    out, i = [], 0
    if in_matrix is None:
        in_matrix = []
    while i < len(lines):
        line = lines[i]
        out.append(line)
        in_matrix.append(False)
        i += 1
        m = re.match(r"^(\s*)matrix:\s*(#.*)?$", line)
        if not m:
            continue
        indent = len(m.group(1))
        block = []
        while i < len(lines):
            stripped = lines[i].strip()
            cur_indent = len(lines[i]) - len(lines[i].lstrip())
            if stripped and not stripped.startswith("#") and cur_indent <= indent:
                break
            block.append(lines[i])
            i += 1
        block, is_matrix = update_matrix_block(block)
        out.extend(block)
        in_matrix.extend([is_matrix] * len(block))
    return "\n".join(out)


# "3.11" or "py311", not part of a longer version like "1.3.11" or "3.110".
# Only 3.8+ is considered, so that unrelated numbers like "3.5" are not flagged.
VERSION_RE = re.compile(r"(?:^|[^0-9.])(?:3\.|py3)(\d+)(?![0-9])")
# tox-style "py{311,312}"
TOX_ENVS_RE = re.compile(r"py\{([\d,\s]+)\}")
PYTHON_RE = re.compile(r"python|py3\d", re.I)

# Lines in pyproject.toml that update_pyproject() keeps in sync.
MANAGED_PYPROJECT_RE = re.compile(
    r"requires-python|Programming Language :: Python :: 3\.|target-version"
    r"|envlist\s*=\s*py\{|^\s*3\.\d+\s*:\s*py3\d+"
)

# Files where version mentions are noise or history rather than config.
REVIEW_EXCLUDE = ["*.lock", "*.ipynb", "*.svg", "CHANGELOG*", "*/CHANGELOG*", "*.min.js"]
MAX_REVIEW_SIZE = 1_000_000


def review_mentions(managed):
    """Tracked-file lines still mentioning a Python version, as "path:line:text".

    Dropped versions are always reported. Other versions are reported only when the
    line (or file name) mentions Python, to skip unrelated numbers. Lines this script
    manages are skipped: `managed` maps a relative path to managed line numbers.
    """
    files = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True, text=True, check=True,
    ).stdout.split("\0")
    found = []
    for rel in filter(None, files):
        path = root / rel
        if any(fnmatch.fnmatch(rel, pat) for pat in REVIEW_EXCLUDE):
            continue
        if not path.is_file() or path.stat().st_size > MAX_REVIEW_SIZE:
            continue
        try:
            text = path.read_text()
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable
        python_file = "python" in rel.lower()
        skip = managed.get(rel, set())
        for n, line in enumerate(text.split("\n"), 1):
            if n in skip:
                continue
            if rel == "pyproject.toml" and MANAGED_PYPROJECT_RE.search(line):
                continue
            versions = VERSION_RE.findall(line) + [
                env[1:] for m in TOX_ENVS_RE.findall(line)
                for env in re.findall(r"3\d+", m)
            ]
            versions = [int(v) for v in versions if int(v) >= 8]
            if not versions:
                continue
            if any(v < lo for v in versions) or python_file or PYTHON_RE.search(line):
                found.append(f"{rel}:{n}:{line.strip()}")
    return found


def validate_toml(path, text):
    try:
        import tomllib
    except ImportError:
        return
    tomllib.loads(text)


def validate_yaml(path, text):
    try:
        import yaml
    except ImportError:
        return
    yaml.safe_load(text)


targets = []
pyproject = root / "pyproject.toml"
if pyproject.is_file():
    targets.append((pyproject, update_pyproject, validate_toml))
workflows = root / ".github" / "workflows"
if workflows.is_dir():
    for wf in sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")]):
        targets.append((wf, update_workflow, validate_yaml))

changed, managed = [], {}
for path, update, validate in targets:
    old = path.read_text()
    if update is update_workflow:
        in_matrix = []
        new = update_workflow(old, in_matrix)
        rel = str(path.relative_to(root))
        managed[rel] = {n for n, m in enumerate(in_matrix, 1) if m}
    else:
        new = update(old)
    if new == old:
        continue
    try:
        validate(path, new)
    except Exception as e:
        print(f"Edited {path} is no longer valid: {e}", file=sys.stderr)
        sys.exit(1)
    path.write_text(new)
    changed.append(str(path.relative_to(root)))

if review_file:
    review_file.write_text("".join(f"{m}\n" for m in review_mentions(managed)))

for c in changed:
    print(f"[INFO]  Updated {c}")
sys.exit(0 if changed else 2)
