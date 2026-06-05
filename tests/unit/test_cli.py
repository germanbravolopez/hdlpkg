"""Unit tests for the hdlpkg CLI.

The CLI is exercised in-process via ``cli.main(argv)`` so no subprocess is needed;
output is captured with pytest's ``capsys``.
"""

from __future__ import annotations

import pytest

from hdl_ip_packager import __version__, cli

pytestmark = pytest.mark.unit


def test_no_args_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main([])
    assert rc == 0
    assert "usage" in capsys.readouterr().out.lower()


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_info_reports_manifest(write_manifest, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_manifest()
    rc = cli.main(["info", str(path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "acme:comm:uart:1.2.0" in out
    assert "acme:common:fifo" in out
    assert "rtl" in out and "sim" in out


def test_validate_ok(write_manifest, capsys: pytest.CaptureFixture[str]) -> None:
    path = write_manifest()
    rc = cli.main(["validate", str(path)])
    assert rc == 0
    assert "valid manifest" in capsys.readouterr().out


def test_validate_bad_manifest_returns_one(
    write_manifest, capsys: pytest.CaptureFixture[str]
) -> None:
    path = write_manifest('[package]\nvendor="a"\n')  # missing required keys
    rc = cli.main(["validate", str(path)])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


def test_missing_manifest_file_returns_one(capsys: pytest.CaptureFixture[str]) -> None:
    rc = cli.main(["info", "definitely_not_here.toml"])
    assert rc == 1
    assert "error:" in capsys.readouterr().err


@pytest.mark.parametrize("command", ["resolve", "install", "pack", "publish", "pull"])
def test_planned_commands_report_not_implemented(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = cli.main([command])
    assert rc == 2
    assert "not implemented" in capsys.readouterr().err.lower()


def test_build_parser_is_constructable() -> None:
    parser = cli.build_parser()
    assert parser.prog == "hdlpkg"
