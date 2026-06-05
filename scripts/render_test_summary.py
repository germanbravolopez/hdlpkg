#!/usr/bin/env python3
"""Render a foldable Markdown test report from pytest's JUnit XML.

Reads one or more JUnit XML files (produced by ``pytest --junitxml=...``) and
emits a Markdown report: a top-level pass/fail heading with totals, then one
collapsible ``<details>`` section per test group (class or module) with a
per-test table. Failure/error messages are shown beneath each group.

When ``GITHUB_STEP_SUMMARY`` is set (in GitHub Actions) the report is appended
there so it shows up on the run's summary page; otherwise it is written to
stdout, so the script is equally useful locally::

    pytest --junitxml=test-results.xml
    python scripts/render_test_summary.py --title "Test results"

This script only *renders*; it never runs tests and always exits 0. The CI job
runs pytest (the gate) and calls this afterwards, preserving pytest's exit code.

Pure standard library - no third-party dependencies - so it runs anywhere a
Python interpreter does, on any OS.
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

PASS = "✅"  # white check mark
FAIL = "❌"  # cross mark
SKIP = "⚠️"  # warning sign


@dataclass
class Case:
    name: str
    time: float
    status: str  # "passed" | "failed" | "error" | "skipped"
    message: str = ""


@dataclass
class Group:
    name: str
    cases: list[Case] = field(default_factory=list)

    @property
    def failed(self) -> int:
        return sum(c.status in ("failed", "error") for c in self.cases)

    @property
    def skipped(self) -> int:
        return sum(c.status == "skipped" for c in self.cases)

    @property
    def icon(self) -> str:
        if self.failed:
            return FAIL
        if self.skipped == len(self.cases) and self.cases:
            return SKIP
        return PASS


def _case_status(node: ET.Element) -> tuple[str, str]:
    """Return (status, message) for a <testcase> element."""
    for tag, status in (("failure", "failed"), ("error", "error"), ("skipped", "skipped")):
        child = node.find(tag)
        if child is not None:
            message = child.get("message", "") or (child.text or "").strip()
            return status, message.splitlines()[0] if message else ""
    return "passed", ""


def collect(paths: list[str]) -> list[Group]:
    """Parse every JUnit file into grouped cases (grouped by testcase classname)."""
    groups: dict[str, Group] = {}
    for path in paths:
        tree = ET.parse(path)
        for case in tree.iter("testcase"):
            name = case.get("name", "?")
            classname = case.get("classname") or "(module)"
            status, message = _case_status(case)
            try:
                elapsed = float(case.get("time", "0") or 0)
            except ValueError:
                elapsed = 0.0
            groups.setdefault(classname, Group(classname)).cases.append(
                Case(name=name, time=elapsed, status=status, message=message)
            )
    return [groups[k] for k in sorted(groups)]


def _md_cell(text: str) -> str:
    """Escape a string so it is safe inside a one-line Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render(groups: list[Group], title: str) -> str:
    total = sum(len(g.cases) for g in groups)
    failed = sum(g.failed for g in groups)
    skipped = sum(g.skipped for g in groups)
    icon = {True: FAIL, False: PASS}[failed > 0]

    lines: list[str] = [
        f"## {icon} {title}",
        "",
        f"**{total} tests, {failed} failed, {skipped} skipped** across {len(groups)} group(s)",
        "",
    ]
    if not groups:
        lines.append("_No JUnit results found._")
        return "\n".join(lines)

    icon_for = {"passed": PASS, "failed": FAIL, "error": FAIL, "skipped": SKIP}
    for g in groups:
        open_attr = " open" if g.failed else ""
        lines.append(
            f"<details{open_attr}><summary>{g.icon} <b>{g.name}</b> - "
            f"{len(g.cases)} tests, {g.failed} failed</summary>"
        )
        lines += ["", "| Result | Test | Time (s) |", "| :----: | ---- | -------: |"]
        for c in g.cases:
            lines.append(f"| {icon_for[c.status]} | {_md_cell(c.name)} | {c.time:.3f} |")
        failures = [c for c in g.cases if c.status in ("failed", "error") and c.message]
        if failures:
            lines += ["", "Failures:"]
            lines += [f"- `{_md_cell(c.name)}`: {_md_cell(c.message)}" for c in failures]
        lines += ["", "</details>", ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        default=["test-results.xml"],
        help="JUnit XML files or globs (default: test-results.xml)",
    )
    parser.add_argument("--title", default="Test results", help="heading text")
    args = parser.parse_args(argv)

    files: list[str] = []
    for pattern in args.paths:
        files.extend(sorted(glob.glob(pattern)))

    groups = collect(files) if files else []
    report = render(groups, args.title)

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    data = report + "\n"
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(data)
    else:
        # Write UTF-8 bytes directly so the emoji status icons don't crash on a
        # legacy Windows console codepage (cp1252). Fall back to text on the rare
        # stream without a binary buffer.
        buffer = getattr(sys.stdout, "buffer", None)
        if buffer is not None:
            buffer.write(data.encode("utf-8"))
        else:  # pragma: no cover
            sys.stdout.write(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
