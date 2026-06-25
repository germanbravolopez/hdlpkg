"""Integration tests: ``--locked`` fetching from each package's recorded lock ``source``.

Phase 2 of the multi-registry consumer flow: when ``install --locked`` / ``gen --locked``
is run with no ``--registry``/``--search``, each locked package is fetched from the exact
``source`` its lockfile entry recorded -- so a lock that spans several registries installs
straight from the lock with no flags.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from hdlpkg import cli

pytestmark = pytest.mark.integration

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"


@pytest.fixture
def uart_project(tmp_path: Path) -> Path:
    proj = tmp_path / "proj"
    proj.mkdir()
    manifest = proj / "ip.toml"
    shutil.copy(EXAMPLES / "uart" / "ip.toml", manifest)
    return manifest


def test_install_locked_fetches_from_recorded_source_without_registry_flag(
    uart_project: Path, tmp_path: Path
) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0
    # Resolve against the store so the lock records source = "registry:<store>".
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    assert "registry:" in (uart_project.parent / "ip.lock").read_text(encoding="utf-8")

    cache = tmp_path / "cache"
    # No --registry / --search: the dependency must come from the lock's recorded source.
    rc = cli.main(["install", str(uart_project), "--cache-dir", str(cache), "--locked"])
    assert rc == 0
    # The cache was populated, so a following offline gen --locked builds with no registry.
    out = tmp_path / "out"
    assert (
        cli.main(
            [
                "gen",
                "sim",
                str(uart_project),
                "--cache-dir",
                str(cache),
                "--locked",
                "--output",
                str(out),
            ]
        )
        == 0
    )
    assert "sync_fifo.sv" in (out / "uart.vc").read_text(encoding="utf-8")


def test_locked_install_errors_clearly_when_source_is_unreachable(
    uart_project: Path, tmp_path: Path
) -> None:
    store = tmp_path / "store"
    assert cli.main(["publish", str(EXAMPLES / "fifo" / "ip.toml"), "--registry", str(store)]) == 0
    assert cli.main(["resolve", str(uart_project), "--registry", str(store)]) == 0
    # Remove the store so the recorded source no longer resolves.
    shutil.rmtree(store)

    rc = cli.main(
        ["install", str(uart_project), "--cache-dir", str(tmp_path / "cache"), "--locked"]
    )
    assert rc != 0  # fails closed rather than silently producing nothing
