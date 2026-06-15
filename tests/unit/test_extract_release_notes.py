"""Unit tests for ``scripts/extract_release_notes.py``.

The release workflow uses this to build the GitHub Release body, so its pure text
logic is tested directly. The script lives outside the importable package (under
``scripts/``), so it is loaded by file path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "extract_release_notes.py"


def _load():
    spec = importlib.util.spec_from_file_location("extract_release_notes", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ern = _load()

TRACKER = (
    "## Completed Milestones\n"
    "\n"
    "### Release 0.8.0 — June 2026\n"
    "- [x] **Tagged `0.8.0`**: completeness pass + backlog batch.\n"
    "  Second line of the entry.\n"
    "\n"
    "### Release 0.7.0 — June 2026\n"
    "- [x] **Tagged `0.7.0`**: SBOM.\n"
    "\n"
    "## Archive\n"
    "- old stuff\n"
)


def test_extract_section_returns_only_that_release() -> None:
    section = ern.extract_section(TRACKER, "0.8.0")
    assert section is not None
    assert "completeness pass" in section
    assert "Second line of the entry." in section
    # Stops at the next heading -- the 0.7.0 entry and Archive must not bleed in.
    assert "0.7.0" not in section
    assert "old stuff" not in section


def test_extract_section_missing_returns_none() -> None:
    assert ern.extract_section(TRACKER, "9.9.9") is None


def test_extract_section_does_not_match_version_prefix() -> None:
    # "0.8" must not match the "0.8.0" heading (word-boundary guard).
    assert ern.extract_section(TRACKER, "0.8") is None


def test_build_release_body_includes_summary_and_pypi_link() -> None:
    body = ern.build_release_body(TRACKER, "0.8.0")
    assert "completeness pass" in body
    assert "https://pypi.org/project/hdlpkg/0.8.0/" in body


def test_build_release_body_falls_back_when_no_entry() -> None:
    body = ern.build_release_body(TRACKER, "1.0.0-rc.1")
    assert "Release 1.0.0-rc.1." in body
    assert "https://pypi.org/project/hdlpkg/1.0.0-rc.1/" in body


def test_build_release_body_respects_project_slug() -> None:
    body = ern.build_release_body(TRACKER, "0.8.0", project="other-pkg")
    assert "https://pypi.org/project/other-pkg/0.8.0/" in body


def test_main_ok(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    tracker = tmp_path / "progress_tracker.md"
    tracker.write_text(TRACKER, encoding="utf-8")
    rc = ern.main(["--version", "0.8.0", "--tracker", str(tracker)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "completeness pass" in out
    assert "pypi.org/project/hdlpkg/0.8.0/" in out


def test_main_missing_version_returns_one(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ern.main(["--version", "", "--tracker", str(_SCRIPT)])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_main_missing_tracker_returns_one(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = ern.main(["--version", "0.8.0", "--tracker", str(tmp_path / "nope.md")])
    assert rc == 1
    assert "error:" in capsys.readouterr().err
