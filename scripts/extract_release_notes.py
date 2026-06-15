#!/usr/bin/env python3
"""Build the body for a tag's GitHub Release from the progress tracker.

The release workflow (``.github/workflows/release.yml``) creates a GitHub Release
for each ``X.Y.Z`` tag. Its body is a short summary of what shipped plus a link to
the published PyPI page. ``docs/progress_tracker.md`` is the project's changelog
source: every release adds a ``### Release X.Y.Z -- <Month Year>`` entry under
Completed Milestones, so this script lifts that section out and appends the PyPI
link.

The text logic is pure (it takes the tracker text + version as arguments), so it is
unit-tested directly; only ``main`` reads the environment and the file. Pure
standard library.

Usage (CI sets ``GITHUB_REF_NAME`` to the tag name automatically)::

    python scripts/extract_release_notes.py
    python scripts/extract_release_notes.py --version 1.2.3 --tracker docs/progress_tracker.md
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

#: PyPI project slug (the distribution name, with the dashes PyPI normalizes to).
_PYPI_PROJECT = "hdlpkg"

#: A markdown heading at the section level used for release entries, or shallower.
_HEADING = re.compile(r"^#{2,3}\s")


def extract_section(tracker_text: str, version: str) -> str | None:
    """Return the ``### Release <version>`` section body, or ``None`` if absent.

    The body is every line after the heading up to (but excluding) the next ``##``
    or ``###`` heading, with surrounding blank lines stripped.
    """
    heading = re.compile(rf"^###\s+Release\s+{re.escape(version)}(?:\s|$)")
    lines = tracker_text.splitlines()
    for i, line in enumerate(lines):
        if heading.match(line):
            body: list[str] = []
            for following in lines[i + 1 :]:
                if _HEADING.match(following):
                    break
                body.append(following)
            return "\n".join(body).strip() or None
    return None


def build_release_body(tracker_text: str, version: str, project: str = _PYPI_PROJECT) -> str:
    """Compose the GitHub Release body: the tracker summary + a PyPI link.

    Falls back to a one-line summary when the tracker has no entry for *version*
    (e.g. a pre-release that was not recorded), so the workflow never fails on a
    missing section.
    """
    section = extract_section(tracker_text, version)
    summary = section if section is not None else f"Release {version}."
    pypi_url = f"https://pypi.org/project/{project}/{version}/"
    return f"{summary}\n\n---\nPublished to PyPI: {pypi_url}\n"


def main(argv: list[str] | None = None) -> int:
    """Read the tracker + version, print the release body, and return an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=os.environ.get("GITHUB_REF_NAME", ""),
        help="release version / tag name (default: $GITHUB_REF_NAME)",
    )
    parser.add_argument(
        "--tracker",
        default="docs/progress_tracker.md",
        help="path to the progress tracker",
    )
    parser.add_argument("--project", default=_PYPI_PROJECT, help="PyPI project slug")
    args = parser.parse_args(argv)

    if not args.version:
        print("error: no version given (set --version or $GITHUB_REF_NAME)", file=sys.stderr)
        return 1
    try:
        tracker_text = Path(args.tracker).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(build_release_body(tracker_text, args.version, args.project))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
