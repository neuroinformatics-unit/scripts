#!/usr/bin/env python3

import re
import sys
import urllib.request
import json
from pathlib import Path

README_PATH = Path(sys.argv[1])
REPO        = sys.argv[2]
ORG         = sys.argv[3]


def _github_head_ok(url: str) -> bool:
    """HEAD a GitHub URL; returns True on 200, False on 404 or any error."""
    try:
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", "Mozilla/5.0 BrainGlobe-Badge-Updater/1.0")
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status == 200
    except urllib.error.HTTPError as e:
        return e.code == 200   # always false for 404/403
    except Exception:
        return False

def conda_exists(pkg: str) -> bool:
    feedstock = pkg.replace("_", "-").lower()
    return _github_head_ok(
        f"https://github.com/conda-forge/{feedstock}-feedstock"
    )

def napari_hub_exists(pkg: str) -> bool:
    """Any 'Framework :: napari' classifier means the package
    declares napari support and will appear on the hub."""
    try:
        req = urllib.request.Request(
            f"https://pypi.org/pypi/{pkg}/json",
            headers={"User-Agent": "BrainGlobe-Badge-Updater/1.0"}
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read())
        classifiers = data.get("info", {}).get("classifiers", [])
        return any("napari" in c.lower() for c in classifiers)
    except Exception:
        return False

raw = README_PATH.read_text(encoding="utf-8")

# 1.Strip all existing badge lines from the raw text

BADGE_LINE_RE = re.compile(r"^[ \t]*\[!\[.*\n?", re.MULTILINE)

CONTINUATION_LINE_RE = re.compile(r"^[ \t]+https?://[^\s]+\)\s*\n?", re.MULTILINE)

def strip_all_badge_lines(text: str) -> str:
    cleaned = BADGE_LINE_RE.sub("", text)
    cleaned = CONTINUATION_LINE_RE.sub("", cleaned)
    # collapse runs of 3+ newlines to 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned

stripped = strip_all_badge_lines(raw)

# 2.Detect metadata

# 2a.PyPI package name
pypi_match = re.search(r"pypi\.org/project/([A-Za-z0-9_\-]+)", raw, re.IGNORECASE)
pypi_pkg_norm = (pypi_match.group(1) if pypi_match else REPO).replace("_", "-").lower()

# 2b.DOI - search citation section first, then whole file
doi = None

def _find_doi_in_text(text: str):
    """Return the first package-level DOI found in text, or None."""
    for line in text.splitlines():
        # Skip table rows
        if line.lstrip().startswith("|"):
            continue

        # Pattern 1 - plain doi.org link
        m = re.search(
            r"https://doi\.org/(10\.[0-9]{4,}/[^\s\)\]\"',;<>]+)", line
        )
        if m:
            return m.group(1).rstrip(".,;)")

        # Pattern 2 - shields.io badge with percent-encoded DOI
        m = re.search(
            r"/badge/DOI-(10\.[0-9]{4,}[^\s\"'<>\-]*(?:%2F[^\s\"'<>\-]+)+)",
            line, re.IGNORECASE
        )
        if m:
            raw_doi = m.group(1).rstrip(".,;)")
            return raw_doi.replace("%2F", "/").replace("%2f", "/")

    return None

# Search citation section before falling back to whole file
cit_match = re.search(r"(?:^|\n)#{1,3} Cit", raw, re.IGNORECASE)
if cit_match:
    doi = _find_doi_in_text(raw[cit_match.start():])
if not doi:
    doi = _find_doi_in_text(raw)

# 2c.CI workflow file
workflow_file = "test_and_deploy.yml"

# 2d.Docs URL
DOCS_FALLBACK = "https://brainglobe.info/documentation/index.html"
docs_url = None

# 1.PyPI metadata
try:
    _pypi_req = urllib.request.Request(
        f"https://pypi.org/pypi/{pypi_pkg_norm}/json",
        headers={"User-Agent": "BrainGlobe-Badge-Updater/1.0"}
    )
    with urllib.request.urlopen(_pypi_req, timeout=8) as _r:
        _pypi_data = json.loads(_r.read())
    _project_urls = _pypi_data.get("info", {}).get("project_urls") or {}
    # Check all URL keys case-insensitively for 'doc'
    for _key, _val in _project_urls.items():
        if "doc" in _key.lower() and _val and "brainglobe.info/documentation" in _val:
            docs_url = _val.rstrip("/")
            break
except Exception:
    pass  # network err - fall through to README scan

# 2.README scan fallback - search STRIPPED text only
if not docs_url:
    _bare_doc = re.search(
        r"https://brainglobe\.info/documentation/([^\s\"'\)\]]+)", stripped
    )
    if _bare_doc:
        _parts = _bare_doc.group(1).rstrip("/").split("/")
        docs_url = f"https://brainglobe.info/documentation/{_parts[0]}/index.html"

# 3.fallback
if not docs_url:
    docs_url = DOCS_FALLBACK

print(f"  docs_url={docs_url}", flush=True)

# 2e.License
license_badge_url = "https://img.shields.io/badge/License-BSD%203--Clause-blue.svg"
license_link      = "https://opensource.org/licenses/BSD-3-Clause"

try:
    _pypi_req = urllib.request.Request(
        f"https://pypi.org/pypi/{pypi_pkg_norm}/json",
        headers={"User-Agent": "Badge-Updater/1.0"}
    )
    with urllib.request.urlopen(_pypi_req, timeout=8) as _r:
        _pypi_data = json.loads(_r.read())
    classifiers = _pypi_data.get("info", {}).get("classifiers", [])
    for c in classifiers:
        if "MIT" in c:
            license_badge_url = "https://img.shields.io/badge/License-MIT-blue.svg"
            license_link      = "https://opensource.org/licenses/MIT"
            break
except Exception:
    pass

# 2f.Codecov token
codecov_token = ""
cc_match = re.search(
    r"codecov\.io/gh/[^/]+/" + re.escape(REPO) + r"/[^\s\"'\)]*\?token=([A-Za-z0-9]+)",
    raw
)
if cc_match:
    codecov_token = f"?token={cc_match.group(1)}"

# 2g.Check for conda-forge and napari-hub presence
has_conda  = conda_exists(pypi_pkg_norm)
has_napari = napari_hub_exists(pypi_pkg_norm)

print(
    f"  pkg={pypi_pkg_norm}  doi={doi}  workflow={workflow_file}  "
    f"conda={has_conda}  napari={has_napari}  docs={docs_url}",
    flush=True
)

# 3.Build the new badge block

gh_base  = f"https://github.com/{ORG}/{REPO}"
pypi_url = f"https://pypi.org/project/{pypi_pkg_norm}"

docs_label = pypi_pkg_norm.replace("-", "--").replace("_", "__").replace("/", "%2F")

lines = []

# Section 1 - Docs / contact
lines.append(
    f"[![Docs](https://img.shields.io/badge/Docs-{docs_label}-blue)]"
    f"({docs_url})"
)
lines.append(
    "[![Get in Touch](https://img.shields.io/badge/Get%20in%20Touch-BrainGlobe-blue)]"
    "(https://brainglobe.info/contact.html)"
)

# Section 2 - DOI
if doi:
    #   "-"  -> "--"
    #   "_"  -> "__"
    #   "/"  -> "%2F"
    doi_encoded = doi.replace("-", "--").replace("_", "__").replace("/", "%2F")
    doi_img = f"https://img.shields.io/badge/DOI-{doi_encoded}-green"
    lines.append(f"[![DOI]({doi_img})](https://doi.org/{doi})")

# Section 3 - License
lines.append(f"[![License]({license_badge_url})]({license_link})")

# Section 4 - CI/coverage
lines.append(
    f"[![Tests](https://img.shields.io/github/actions/workflow/status/"
    f"{ORG}/{REPO}/{workflow_file}?branch=main)]"
    f"({gh_base}/actions)"
)
lines.append(
    f"[![Codecov](https://codecov.io/gh/{ORG}/{REPO}/graph/badge.svg{codecov_token})]"
    f"(https://codecov.io/gh/{ORG}/{REPO})"
)

# Section 5 - Releases
lines.append(
    f"[![Python Version](https://img.shields.io/pypi/pyversions/{pypi_pkg_norm}.svg)]"
    f"({pypi_url})"
)
lines.append(
    f"[![PyPI](https://img.shields.io/pypi/v/{pypi_pkg_norm}.svg)]({pypi_url})"
)
if has_conda:
    lines.append(
        f"[![Conda](https://anaconda.org/conda-forge/{pypi_pkg_norm}/badges/version.svg)]"
        f"(https://anaconda.org/conda-forge/{pypi_pkg_norm})"
    )
if has_napari:
    lines.append(
        f"[![Napari Hub](https://img.shields.io/endpoint?"
        f"url=https://api.napari-hub.org/shields/{pypi_pkg_norm})]"
        f"(https://www.napari-hub.org/plugins/{pypi_pkg_norm})"
    )
lines.append(
    f"[![Downloads](https://static.pepy.tech/badge/{pypi_pkg_norm})]"
    f"(https://pepy.tech/project/{pypi_pkg_norm})"
)

# Section 6 - Contributor tooling
lines.append(
    "[![Code Style: Ruff](https://img.shields.io/endpoint?"
    "url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/format.json)]"
    "(https://github.com/astral-sh/ruff)"
)
lines.append(
    "[![Pre-commit](https://img.shields.io/badge/pre--commit-enabled-green?"
    "logo=pre-commit&logoColor=white)]"
    "(https://github.com/pre-commit/pre-commit)"
)
lines.append(
    "[![Contributions Welcome](https://img.shields.io/badge/Contributions-Welcome-green.svg)]"
    "(https://brainglobe.info/community/developers/index.html)"
)

new_badge_block = "\n".join(lines)

# 4.Insert the new badge block into the stripped README text, just before the first heading

first_heading = re.search(r"^#", stripped, re.MULTILINE)

if first_heading:
    insert_at = first_heading.start()
    preamble = stripped[:insert_at].strip("\n")
    rest     = stripped[insert_at:]
    if preamble:
        new_raw = preamble + "\n\n" + new_badge_block + "\n\n" + rest
    else:
        new_raw = new_badge_block + "\n\n" + rest
else:
    new_raw = new_badge_block + "\n\n" + stripped.lstrip("\n")

README_PATH.write_text(new_raw, encoding="utf-8")
print("  README updated successfully.")