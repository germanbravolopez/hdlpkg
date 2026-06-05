"""Unit tests for ``scripts/check_release_version.py``.

The release workflow trusts this guard to stop a mislabelled publish, so its pure
comparison logic is tested directly. The script lives outside the importable
package (under ``scripts/``), so it is loaded by file path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_release_version.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_release_version", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


crv = _load()

PYPROJECT_OK = '[project]\nname = "x"\nversion = "1.2.3"\n'


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("1.2.3", "1.2.3"),
        ("v1.2.3", "1.2.3"),
        ("refs/tags/1.2.3", "1.2.3"),
        ("refs/tags/v2.0.0-rc.1", "2.0.0-rc.1"),
        ("  1.2.3  ", "1.2.3"),
    ],
)
def test_tag_to_version(ref: str, expected: str) -> None:
    assert crv.tag_to_version(ref) == expected


def test_read_project_version() -> None:
    assert crv.read_project_version(PYPROJECT_OK) == "1.2.3"


def test_read_project_version_missing_raises() -> None:
    with pytest.raises(ValueError):
        crv.read_project_version('[project]\nname = "x"\n')


def test_check_matches_returns_version() -> None:
    assert crv.check("refs/tags/1.2.3", PYPROJECT_OK) == "1.2.3"


def test_check_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="does not match"):
        crv.check("refs/tags/9.9.9", PYPROJECT_OK)


def test_check_empty_ref_raises() -> None:
    with pytest.raises(ValueError):
        crv.check("refs/tags/", PYPROJECT_OK)


def test_main_ok(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT_OK, encoding="utf-8")
    rc = crv.main(["--ref", "1.2.3", "--pyproject", str(pyproject)])
    assert rc == 0
    assert "OK" in capsys.readouterr().out


def test_main_mismatch_returns_one(tmp_path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(PYPROJECT_OK, encoding="utf-8")
    rc = crv.main(["--ref", "refs/tags/2.0.0", "--pyproject", str(pyproject)])
    assert rc == 1
    assert "error:" in capsys.readouterr().err
