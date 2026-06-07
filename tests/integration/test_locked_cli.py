"""Integration tests: reproducible, lockfile-driven `install --locked` / `gen --locked`."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdl_ip_packager import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def uart_project(tmp_path: Path) -> Path:
    """A temp copy of the UART manifest (its FIFO dep is found via --search examples)."""
    manifest = tmp_path / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)
    return manifest


def _resolve(manifest: Path) -> None:
    assert cli.main(["resolve", str(manifest), "--search", str(EXAMPLES)]) == 0
    assert (manifest.parent / "ip.lock").is_file()


def test_install_locked_fetches_exactly_from_lockfile(uart_project: Path, tmp_path, capsys) -> None:
    _resolve(uart_project)
    capsys.readouterr()  # drop resolve output
    rc = cli.main(
        [
            "install",
            str(uart_project),
            "--search",
            str(EXAMPLES),
            "--cache-dir",
            str(tmp_path / "c"),
            "--locked",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "locked package(s)" in out
    assert "acme:common:fifo:1.0.0" in out


def test_install_locked_without_lockfile_fails(uart_project: Path, tmp_path, capsys) -> None:
    rc = cli.main(
        [
            "install",
            str(uart_project),
            "--search",
            str(EXAMPLES),
            "--cache-dir",
            str(tmp_path / "c"),
            "--locked",
        ]
    )
    assert rc == 1
    assert "--locked needs an existing" in capsys.readouterr().err


def test_gen_locked_pins_dependency_from_lockfile(uart_project: Path, tmp_path) -> None:
    _resolve(uart_project)
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--search",
            str(EXAMPLES),
            "--output",
            str(tmp_path / "out"),
            "--locked",
        ]
    )
    assert rc == 0
    vc = (tmp_path / "out" / "uart.vc").read_text(encoding="utf-8")
    assert "sync_fifo.sv" in vc  # the locked FIFO dependency was pulled in


def test_gen_locked_without_lockfile_fails(uart_project: Path, tmp_path, capsys) -> None:
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--search",
            str(EXAMPLES),
            "--output",
            str(tmp_path / "out"),
            "--locked",
        ]
    )
    assert rc == 1
    assert "--locked needs an existing" in capsys.readouterr().err
