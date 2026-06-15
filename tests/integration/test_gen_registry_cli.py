"""Integration tests: ``gen`` consuming dependencies from a registry / the cache (#13).

Before this, ``gen`` could only reach loose dependency source trees via ``--search``;
a published or installed core (which lives as a ``.ipkg`` blob, not a loose tree) was
unreachable. These tests cover the three paths ``gen`` now supports for a dependency:
fetch-and-extract from a published registry (``--registry``), offline reuse of an
installed cache (``install --locked`` then ``gen --locked``), and a clear error when a
locked dependency is neither cached nor reachable.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from hdl_ip_packager import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def store(tmp_path: Path) -> Path:
    """A writable local-store registry with the FIFO core published into it."""
    location = tmp_path / "store"
    fifo = str(EXAMPLES / "fifo" / "ip.toml")
    assert cli.main(["publish", fifo, "--registry", str(location)]) == 0
    return location


@pytest.fixture
def uart_project(tmp_path: Path) -> Path:
    """A temp copy of the UART manifest in its own dir (depends on acme:common:fifo ^1.0.0).

    Kept in a subdir so the default ``--search`` scan of the manifest's parent does not
    accidentally discover the FIFO published into the sibling ``store/``.
    """
    proj = tmp_path / "proj"
    proj.mkdir()
    manifest = proj / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)
    return manifest


def test_gen_from_registry_fetches_and_extracts_dependency(
    store: Path, uart_project: Path, tmp_path: Path
) -> None:
    # No --search: the FIFO dependency must come from the registry, via the cache.
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--registry",
            str(store),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    vc = (tmp_path / "out" / "uart.vc").read_text(encoding="utf-8")
    assert "sync_fifo.sv" in vc  # the dependency's RTL was materialized and included


def test_install_locked_then_gen_locked_works_offline(
    store: Path, uart_project: Path, tmp_path: Path
) -> None:
    cache = tmp_path / "cache"
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    assert (
        cli.main(
            [
                "install",
                str(uart_project),
                "--registry",
                str(store),
                "--cache-dir",
                str(cache),
                "--locked",
            ]
        )
        == 0
    )
    # Now gen with neither --registry nor --search: the dependency is served from the
    # installed cache by the lockfile's digest -- fully offline.
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--cache-dir",
            str(cache),
            "--locked",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 0
    assert "sync_fifo.sv" in (tmp_path / "out" / "uart.vc").read_text(encoding="utf-8")


def test_gen_locked_fails_closed_on_checksum_drift(
    store: Path, uart_project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # gen --locked must verify the fetched digest against the lock, like install --locked.
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    lock = uart_project.parent / "ip.lock"
    tampered = re.sub(
        r'checksum = "sha256:[0-9a-f]+"',
        f'checksum = "sha256:{"0" * 64}"',
        lock.read_text(encoding="utf-8"),
    )
    lock.write_text(tampered, encoding="utf-8")
    capsys.readouterr()
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--registry",
            str(store),
            "--cache-dir",
            str(tmp_path / "cache"),
            "--locked",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 1
    assert "mismatch" in capsys.readouterr().err.lower()


def test_gen_locked_without_cache_or_registry_gives_actionable_error(
    store: Path, uart_project: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    capsys.readouterr()
    # Locked, but nothing installed and no --registry/--search to fetch from.
    rc = cli.main(
        [
            "gen",
            "sim",
            str(uart_project),
            "--cache-dir",
            str(tmp_path / "empty"),
            "--locked",
            "--output",
            str(tmp_path / "out"),
        ]
    )
    assert rc == 1
    err = capsys.readouterr().err
    assert "install" in err and "--locked" in err
