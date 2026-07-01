"""Integration tests: a plain ``install`` builds from an up-to-date ip.lock, no --registry.

Ergonomic improvement: once ``ip.lock`` exists and still satisfies ``ip.toml``, ``hdlpkg
install`` fetches straight from the sources the lock recorded -- no need to repeat
``--registry``. It only re-resolves (which needs a registry/search) when the lock is missing
or stale, when dependencies are added, or when ``--update`` is passed.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A UART consumer with the FIFO dependency available as a loose sibling core.

    Keeping fifo in the manifest's own directory means the default (no-flag) resolve scan
    can find it, so the re-resolve paths work without a registry.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    shutil.copy(EXAMPLES / "uart" / "ip.toml", proj / "ip.toml")
    shutil.copytree(EXAMPLES / "fifo", proj / "fifo")
    return proj / "ip.toml"


def test_plain_install_builds_from_an_uptodate_lock_without_registry(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0
    assert cli.main(["resolve", str(project), "--registry", str(store)]) == 0
    capsys.readouterr()

    # No --registry: the up-to-date lock drives the install straight from its recorded source.
    rc = cli.main(["install", str(project), "--cache-dir", str(tmp_path / "cache")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "up to date with ip.toml" in out
    assert "acme:common:fifo:1.0.0" in out
    assert any((tmp_path / "cache").rglob("*"))


def test_plain_install_reports_and_reresolves_a_stale_lock(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0
    assert cli.main(["resolve", str(project), "--registry", str(store)]) == 0
    # Tighten the constraint past the locked 1.0.0 so the lock no longer satisfies ip.toml.
    assert cli.main(["add", "acme:common:fifo@^2.0.0", str(project)]) == 0
    capsys.readouterr()

    # Plain install (no flags): it must notice the lock is stale and re-resolve. No 2.x exists
    # locally, so the re-resolve fails -- which proves the stale path (not the lock) was taken.
    rc = cli.main(["install", str(project)])
    err = capsys.readouterr().err
    assert "out of date with ip.toml" in err
    assert rc != 0


def test_update_forces_a_reresolve_even_when_the_lock_is_current(
    project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0
    assert cli.main(["resolve", str(project), "--registry", str(store)]) == 0
    capsys.readouterr()

    # --update bypasses the up-to-date lock; with no --registry it re-resolves via the default
    # local scan (which finds the sibling fifo) and rewrites the lock.
    rc = cli.main(["install", str(project), "--update", "--cache-dir", str(tmp_path / "c")])
    assert rc == 0
    out = capsys.readouterr().out
    assert "wrote" in out  # a fresh resolve rewrote the lockfile


def test_locked_and_update_are_mutually_exclusive(project: Path) -> None:
    rc = cli.main(["install", str(project), "--locked", "--update"])
    assert rc != 0
