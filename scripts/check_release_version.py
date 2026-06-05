#!/usr/bin/env python3
"""Guard a tag-driven release: the git tag must match the packaged version.

The release workflow (``.github/workflows/release.yml``) fires on an ``X.Y.Z`` tag
and publishes whatever ``python -m build`` produces -- which takes its version from
``[project].version`` in ``pyproject.toml``. If the tag and that version disagree,
the wrong artifact gets published under the tag's name. This script fails the job
before the build when they differ.

The comparison logic is pure (it takes the ref and the ``pyproject.toml`` text as
arguments), so it is unit-tested directly; only ``main`` reads the environment and
the file. Pure standard library -- ``tomllib`` ships with Python 3.11+.

Usage (CI sets ``GITHUB_REF`` to ``refs/tags/<tag>`` automatically)::

    python scripts/check_release_version.py
    python scripts/check_release_version.py --ref 1.2.3 --pyproject pyproject.toml
"""

from __future__ import annotations

import argparse
import os
import sys
import tomllib
from pathlib import Path

_TAG_REF_PREFIX = "refs/tags/"


def tag_to_version(ref: str) -> str:
    """Reduce a git ref or tag to a bare version (strip ``refs/tags/`` and a ``v``)."""
    tag = ref.strip()
    if tag.startswith(_TAG_REF_PREFIX):
        tag = tag[len(_TAG_REF_PREFIX) :]
    if tag.startswith("v"):
        tag = tag[1:]
    return tag


def read_project_version(pyproject_text: str) -> str:
    """Return ``[project].version`` from the given ``pyproject.toml`` text."""
    data = tomllib.loads(pyproject_text)
    project = data.get("project")
    if not isinstance(project, dict) or "version" not in project:
        raise ValueError("pyproject.toml has no [project].version")
    return str(project["version"])


def check(ref: str, pyproject_text: str) -> str:
    """Return the agreed version, or raise ``ValueError`` if tag and package differ."""
    tag_version = tag_to_version(ref)
    project_version = read_project_version(pyproject_text)
    if not tag_version:
        raise ValueError(f"Could not derive a version from ref {ref!r}")
    if tag_version != project_version:
        raise ValueError(
            f"Tag version {tag_version!r} does not match [project].version "
            f"{project_version!r} in pyproject.toml; bump the version or fix the tag."
        )
    return tag_version


def main(argv: list[str] | None = None) -> int:
    """Read the ref + pyproject, compare, and return a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ref",
        default=os.environ.get("GITHUB_REF", ""),
        help="git ref or tag (default: $GITHUB_REF)",
    )
    parser.add_argument("--pyproject", default="pyproject.toml", help="path to pyproject.toml")
    args = parser.parse_args(argv)

    try:
        version = check(args.ref, Path(args.pyproject).read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"OK: tag matches packaged version {version}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
