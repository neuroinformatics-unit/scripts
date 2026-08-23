#!/usr/bin/env python3

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

WORKFLOW_PATH  = Path(sys.argv[1])
PYPROJECT_PATH = Path(sys.argv[2])

GITHUB_API = 'https://api.github.com'

SHA_RE = re.compile(r'^[0-9a-f]{40}$')

ACTION_REF_RE = re.compile(
    r'^(?P<indent>\s*)(?P<dash>-\s*)?uses:\s*'
    r'(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+)'
    r'(?P<subpath>(?:/[A-Za-z0-9_.-]+)*)'
    r'@(?P<ref>[A-Za-z0-9_.\-/]+)'
    r'(?:\s*#.*)?\s*$'
)

UNPINNED_ACTIONS = {
    'pypa/gh-action-pypi-publish',
    'actions/download-artifact',
}

_release_cache = {}
_sha_cache = {}

def _github_api_get(path: str):
    req = urllib.request.Request(
        GITHUB_API + path,
        headers={
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'gha-action-pinner',
            **(
                {'Authorization': f"Bearer {os.environ['GITHUB_TOKEN']}"}
                if os.environ.get('GITHUB_TOKEN') else {}
            ),
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)

def latest_release_tag(owner: str, repo: str):
    key = (owner, repo)
    if key in _release_cache:
        return _release_cache[key]

    tag = None
    try:
        data = _github_api_get(f'/repos/{owner}/{repo}/releases/latest')
        tag = data.get('tag_name')
    except urllib.error.HTTPError as e:
        if e.code != 404:
            print(f'  [WARN] GitHub API error fetching {owner}/{repo} latest release: {e}')
    except Exception as e:
        print(f'  [WARN] Could not reach GitHub API for {owner}/{repo}: {e}')

    if not tag:
        try:
            tags = _github_api_get(f'/repos/{owner}/{repo}/tags')
            if tags:
                tag = tags[0]['name']
        except Exception as e:
            print(f'  [WARN] Could not list tags for {owner}/{repo}: {e}')

    _release_cache[key] = tag
    return tag

def resolve_ref_to_sha(owner: str, repo: str, ref: str):
    key = (owner, repo, ref)
    if key in _sha_cache:
        return _sha_cache[key]

    sha = None
    for ref_type in ('tags', 'heads'):
        try:
            data = _github_api_get(f'/repos/{owner}/{repo}/git/ref/{ref_type}/{ref}')
        except Exception:
            continue

        obj = data.get('object', {})
        sha = obj.get('sha')
        if obj.get('type') == 'tag':
            try:
                tag_obj = _github_api_get(f'/repos/{owner}/{repo}/git/tags/{sha}')
                sha = tag_obj.get('object', {}).get('sha', sha)
            except Exception as e:
                print(f'  [WARN] Could not dereference annotated tag {owner}/{repo}@{ref}: {e}')
        break

    _sha_cache[key] = sha
    return sha

def format_release_tag(tag: str):
    return tag if tag.startswith('v') else f'v{tag}'

def pin_action_versions(lines: list):
    changed = False
    for i, raw_line in enumerate(lines):
        eol = ''
        line = raw_line
        if line.endswith('\n'):
            line, eol = line[:-1], '\n'

        m = ACTION_REF_RE.match(line)
        if not m:
            continue

        owner   = m.group('owner')
        repo    = m.group('repo')
        subpath = m.group('subpath') or ''
        ref     = m.group('ref')
        dash    = m.group('dash') or ''

        if SHA_RE.match(ref):
            continue

        if f'{owner}/{repo}' in UNPINNED_ACTIONS:
            print(f'  [SKIP-PIN] {owner}/{repo}{subpath}@{ref} left unpinned (excluded)')
            continue

        latest_tag = latest_release_tag(owner, repo)
        if not latest_tag:
            print(f'  [WARN] {owner}/{repo}: no releases/tags found, leaving @{ref} as-is')
            continue

        sha = resolve_ref_to_sha(owner, repo, latest_tag)
        if not sha:
            print(f'  [WARN] {owner}/{repo}@{latest_tag}: could not resolve commit SHA, leaving @{ref} as-is')
            continue

        formatted_tag = format_release_tag(latest_tag)
        new_line = f"{m.group('indent')}{dash}uses: {owner}/{repo}{subpath}@{sha} # {formatted_tag}"
        if new_line != line:
            lines[i] = new_line + eol
            changed = True
            print(f'  [PIN] {owner}/{repo}{subpath}@{ref} -> {owner}/{repo}{subpath}@{sha} # {formatted_tag}')

    return changed

def has_separate_napari_extra(pyproject: str):
    m = re.search(r'\[project\.optional-dependencies\](.*?)(?=\n\[|\Z)',
                  pyproject, re.DOTALL)
    if not m:
        return False
    return bool(re.search(r'^napari\s*=\s*\[', m.group(1), re.MULTILINE))


def workflow_uses_headless(workflow: str):
    xvfb_true = re.search(
        r'use-xvfb:\s*[\'"]?true[\'"]?\s*(?:#.*)?$', workflow,
        re.IGNORECASE | re.MULTILINE,
    )
    return bool(
        'pyvista/setup-headless-display-action' in workflow
        or xvfb_true
        or 'headless-gui' in workflow
    )


def get_install_extras(pyproject: str, napari_extra: bool):
    if not napari_extra:
        return 'dev'
    m = re.search(r'\[testenv\](.*?)(?=\n\[|\Z)', pyproject, re.DOTALL)
    if m and re.search(r'\bnapari\b', m.group(1)):
        return 'dev,napari'
    return 'dev'



def find_step_blocks(lines: list):
    blocks      = []
    in_steps    = False
    step_indent = None
    block_start = None

    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        ind = len(line) - len(line.lstrip())

        if re.match(r'\s*steps\s*:', line):
            if block_start is not None:
                blocks.append((block_start, i))
                block_start = None
            in_steps    = True
            step_indent = None
            continue

        if in_steps:
            if s.startswith('- ') or s == '-':
                if step_indent is None:
                    step_indent = ind
                if ind == step_indent:
                    if block_start is not None:
                        blocks.append((block_start, i))
                    block_start = i
            elif step_indent is not None and ind <= step_indent and not s.startswith('-'):
                if block_start is not None:
                    blocks.append((block_start, i))
                    block_start = None
                in_steps    = False
                step_indent = None

    if block_start is not None:
        blocks.append((block_start, len(lines)))
    return blocks


def step_base_indent(lines: list, start: int):
    for i in range(start, min(start + 5, len(lines))):
        if lines[i].strip().startswith('-'):
            return ' ' * (len(lines[i]) - len(lines[i].lstrip()))
    return '      '


def extract_kv(block: str, key: str, default: str = ''):
    m = re.search(
        rf'^\s*{re.escape(key)}:\s*["\']?([^\n"\']+)["\']?',
        block, re.MULTILINE
    )
    return m.group(1).strip() if m else default


def test_uv_block(
    ind: str,
    python_version: str,
    install_extras: str,
    use_headless: bool,
    codecov_flags:      str = '',
    install_main_branch: str = '',
    name:      str = 'Run tests',
    condition: str = '',
):
    p = ind + '  '
    w = ind + '    '
    lines = [f'{ind}- name: {name}']
    if condition:
        lines.append(f'{p}if: {condition}')
    lines.append(f'{p}uses: neuroinformatics-unit/actions/test-uv@main')
    lines.append(f'{p}with:')
    lines.append(f'{w}python-version: "{python_version}"')
    lines.append(f'{w}secret-codecov-token: ${{{{ secrets.CODECOV_TOKEN }}}}')
    if install_extras and install_extras != 'dev':
        lines.append(f"{w}install-extras: '{install_extras}'")
    if use_headless:
        lines.append(f"{w}use-headless: 'true'")
    if codecov_flags:
        lines.append(f'{w}codecov-flags: "{codecov_flags}"')
    if install_main_branch:
        lines.append(f"{w}install-main-branch: '{install_main_branch}'")
    lines.append('')
    return '\n'.join(lines) + '\n'

def is_headless_setup_step(block: str):
    uses_m = re.search(r'^\s*(?:-\s*)?uses:\s*(\S+)', block, re.MULTILINE)
    uses_target = uses_m.group(1) if uses_m else ''
    return (
        'pyvista/setup-headless-display-action' in uses_target
        or 'headless-gui' in uses_target
    )

def remove_headless_setup(lines: list):
    changes = []
    blocks = find_step_blocks(lines)

    for i, (start, end) in enumerate(blocks):
        block = ''.join(lines[start:end])

        if is_headless_setup_step(block):
            changes.append((start, end, None))
            print('  [REMOVE] Headless display setup')

            if i > 0:
                prev_start, prev_end = blocks[i - 1]
                prev_block = ''.join(lines[prev_start:prev_end])

                if 'tlambert03/setup-qt-libs' in prev_block:
                    changes.append((prev_start, prev_end, None))
                    print('  [REMOVE] setup-qt-libs')

    for start, end, _ in sorted(changes, key=lambda x: x[0], reverse=True):
        del lines[start:end]

    return bool(changes)

def setup_uv_block(ind: str, python_version: str):
    p = ind + '  '
    w = ind + '    '
    return (
        f'{ind}- name: Install uv\n'
        f'{p}uses: astral-sh/setup-uv@fac544c07dec837d0ccb6301d7b5580bf5edae39 # v8.2.0\n'
        f'{p}with:\n'
        f'{w}enable-cache: true\n'
        f'{w}python-version: "{python_version}"\n'
        f'{w}cache-dependency-glob: "**/pyproject.toml"\n'
        f'{w}activate-environment: true\n'
    )

def extract_job_name(lines: list, step_start: int, default: str = ''):
    step_indent = len(lines[step_start]) - len(lines[step_start].lstrip())

    for i in range(step_start - 1, -1, -1):
        line = lines[i]
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == step_indent - 4 and line.strip().endswith(':'):
            job_start = i

            for j in range(job_start + 1, step_start):
                name_line = lines[j]
                name_indent = len(name_line) - len(name_line.lstrip())

                if name_indent <= indent:
                    break

                m = re.match(
                    r'^\s*name:\s*(?:"([^"]*)"|\'([^\']*)\'|([^\n]*))\s*$',
                    name_line,
                )
                if m:
                    return next(
                        (
                            value.strip()
                            for value in m.groups()
                            if value is not None
                        ),
                        default,
                    )
            return default
    return default


def migrate_workflow(
    path: Path,
    install_extras: str,
    use_headless: bool,
):
    if not path.exists():
        print(f'  [SKIP] Workflow not found: {path}')
        return False

    text = path.read_text(encoding='utf-8')
    original = text

    lines   = text.splitlines(keepends=True)
    changes = []
    remove_headless_setup(lines)

    for start, end in find_step_blocks(lines):
        block = ''.join(lines[start:end])
        ind   = step_base_indent(lines, start)

        if 'actions/setup-python' in block:
            pyver = extract_kv(block, 'python-version', "3.12").strip('"\'')
            if '${{' in pyver:
                changes.append((start, end, None))
                print('  [REMOVE] setup-python (matrix - uv handles Python)')
            else:
                new = setup_uv_block(ind, pyver)
                changes.append((start, end, new))
                print(f'  [REPLACE] setup-python - setup-uv (py{pyver})')

        elif 'run:' in block and (
            'python -m pip install' in block or 'python -m pytest' in block
        ):
            new = block
            new = re.sub(r'[ \t]*python -m pip install --upgrade pip.*\n', '', new)
            new = new.replace('python -m pip install', 'uv pip install')
            new = new.replace('python -m pytest', 'pytest')
            # quote bare local-path extras, e.g. `uv pip install .[dev]`
            # to `uv pip install ".[dev]"`
            new = re.sub(
                r'(uv pip install )(\.\[[^\]\s"\']+\])(?!["\'])',
                r'\1"\2"',
                new,
            )
            if 'shell:' not in new:
                new = re.sub(r'(\s+run:\s)', rf'\n{ind}  shell: bash\1', new, count=1)

            # collapse `run: |` blocks that end up with exactly one command
            # left (after comments/blank lines are stripped away) into a
            # single-line `run: <command>` form
            def _collapse_single_line(m: re.Match):
                prefix, body = m.group('prefix'), m.group('body')
                cmd_lines = [
                    l for l in body.splitlines()
                    if l.strip() and not l.strip().startswith('#')
                ]
                if len(cmd_lines) == 1:
                    return f'{prefix}run: {cmd_lines[0].strip()}\n'
                return m.group(0)

            new = re.sub(
                rf'(?P<prefix>^{re.escape(ind)}  )run:\s*\|\n(?P<body>(?:{re.escape(ind)}    .*\n|\s*\n)+?)(?=^{re.escape(ind)}\S|\Z)',
                _collapse_single_line,
                new,
                flags=re.MULTILINE,
            )

            if new != block:
                changes.append((start, end, new))
                print('  [REPLACE] pip/pytest - uv pip / pytest in run step')

        elif (
            'neuroinformatics-unit/actions/test@v2' in block
            and 'napari-dev' in block
        ):
            pyver = extract_kv(
                block, 'python-version', '${{ matrix.python-version }}'
            )
            new = test_uv_block(
                ind, pyver, install_extras, use_headless,
                install_main_branch='napari/napari',
                name='Run tests against napari main',
                condition=(
                    "github.event_name == 'schedule' "
                    "|| github.event_name == 'workflow_dispatch'"
                ),
            )
            changes.append((start, end, new))
            print('  [REPLACE] napari-dev test@v2 - test-uv@main + install-main-branch')

        elif 'neuroinformatics-unit/actions/test@v2' in block:
            pyver = extract_kv(
                block, 'python-version', '${{ matrix.python-version }}'
            )
            flags = extract_kv(block, 'codecov-flags')
            name = extract_kv(block, 'name', '')

            if flags == 'numba':
                name = extract_job_name(lines, start, 'Run tests')

            if not name:
                name = 'Run tests'

            new = test_uv_block(
                ind,
                pyver,
                install_extras,
                use_headless,
                codecov_flags=flags,
                name=name,
            )
            changes.append((start, end, new))
            print(
                f'  [REPLACE] test@v2 - test-uv@main (name="{name}")'
            )

    for start, end, new in sorted(changes, key=lambda x: x[0], reverse=True):
        if new is None:
            del lines[start:end]
        else:
            lines[start:end] = [new]
    lines = ''.join(lines).splitlines(keepends=True)

    pin_action_versions(lines)

    text = ''.join(lines)
    if text == original:
        print('  [SKIP] No workflow changes detected.')
        return False

    path.write_text(text, encoding='utf-8')
    print('  [OK] Workflow migrated.')
    return True


def migrate_pyproject(path: Path):
    if not path.exists():
        print(f'  [SKIP] pyproject.toml not found: {path}')
        return False

    text = path.read_text(encoding='utf-8')
    original = text

    text = re.sub(r'[ \t]*"tox(?:-[a-z-]+)?",?\n', '', text)

    text = re.sub(
        r'\[tool\.tox\]\s*legacy_tox_ini\s*=\s*""".*?"""[\r\n]*',
        '',
        text,
        flags=re.DOTALL,
    )

    def update_addopts(m: re.Match):
        inner = m.group(1).strip('"\'')
        for flag in ('--cov-report=xml', '--color=yes'):
            if flag not in inner:
                inner += f' {flag}'
        inner = re.sub(r'(?<![v\-])-v\b(?!v)', '-vv', inner)
        if '-vv' not in inner:
            inner += ' -vv'
        return f'addopts = "{inner.strip()}"'

    text = re.sub(r'addopts\s*=\s*(["\'].*?["\'])', update_addopts, text)

    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.rstrip() + "\n"

    if text == original:
        print('  [SKIP] pyproject.toml already up to date.')
        return False

    path.write_text(text, encoding='utf-8')
    print('  [OK] pyproject.toml migrated.')
    return True


pyproject_text = PYPROJECT_PATH.read_text(encoding='utf-8') if PYPROJECT_PATH.exists() else ''
workflow_text  = WORKFLOW_PATH.read_text(encoding='utf-8')  if WORKFLOW_PATH.exists() else ''

napari_extra   = has_separate_napari_extra(pyproject_text)
headless       = workflow_uses_headless(workflow_text)
install_extras = get_install_extras(pyproject_text, napari_extra)

print(
    f'  [DETECT] napari_extra={napari_extra}  '
    f'headless={headless}  '
    f'install_extras={install_extras}'
)

wf_changed = migrate_workflow(WORKFLOW_PATH, install_extras, headless)
py_changed = migrate_pyproject(PYPROJECT_PATH)

if not wf_changed and not py_changed:
    sys.exit(2)